\encoding UTF8
\set ON_ERROR_STOP on
-- Vùng ctrl của capstone: năm bảng sổ nạp và sổ chạy. Mẫu của gói đề, FNV-CAP-DBT v1.5, mục 2.3.1.
-- Chạy bằng postgres trên database cap_<đề>_<tên> SAU setup/bootstrap.sql; chạy lại nhiều lần không lỗi.
-- Cột và kiểu là đề xuất của capstone (giả định): spec Finova mới nêu tên bảng, chưa chốt cột
-- (BOOT-001 §3, §9.2; ELT-TQ §5). Được thêm cột; không được bỏ cột, đổi kiểu hay bỏ ràng buộc dưới đây.
-- Mỗi bảng do đúng role ghi nó tạo, để quyền mặc định ở bootstrap.sql có hiệu lực:
--   finova_loader tạo và ghi: source_system, batch_log, load_reject, schema_drift
--   finova_dbt    tạo và ghi: batch_run

set role finova_loader;

-- 1. source_system: nguồn nào có ingested_ts giả lập, tính theo quy tắc nào (INV-T6)
create table if not exists ctrl.source_system (
    source_id        text        primary key,                       -- trùng cột source_id ở landing, ví dụ 'scenario:CAP-KH'
    is_simulated_ts  boolean     not null,                          -- true: ingested_ts lấy từ manifest, không phải giờ database
    ingested_ts_rule text        not null,                          -- ví dụ 'manifest.commit_ts'
    note             text,
    check (length(btrim(ingested_ts_rule)) > 0)
);

-- 2. batch_log: mỗi lần loader xử lý một lô ghi một dòng, không sửa, không xóa
create table if not exists ctrl.batch_log (
    log_id                bigint generated always as identity primary key,  -- thứ tự xử lý thật; T-GUARD dựa vào cột này, không dựa vào giờ
    batch_id              text        not null,
    source_table          text        not null,
    business_date         date,
    ingested_ts           timestamptz,                                      -- chỉ có khi LOADED; bằng commit_ts của manifest
    status                text        not null check (status in ('LOADED', 'REJECTED_BATCH', 'SKIPPED_DUP')),
    reason_code           text,                                             -- bắt buộc khi status khác LOADED
    row_count_declared    integer,                                          -- manifest khai
    row_count_read        integer,                                          -- loader đếm được trong file
    rows_loaded           integer     not null default 0,
    rows_rejected         integer     not null default 0,
    sha256_declared       text,
    content_hash          text,                                             -- SHA-256 hex của nội dung file thực tế; so trùng lô bằng cột này
    flag_codes            text[]      not null default '{}',                -- ví dụ {SNAPSHOT_DROP}
    detail                jsonb       not null default '{}'::jsonb,         -- ví dụ {"drop_pct": 27.5}
    logged_ts             timestamptz not null default now(),               -- giờ ghi sổ: metadata vận hành, không dùng để lọc as-of
    check (status = 'LOADED' or reason_code is not null),
    check (status <> 'LOADED' or ingested_ts is not null),
    check (rows_loaded >= 0 and rows_rejected >= 0)
);
-- một batch_id chỉ LOADED một lần: nạp lại không sinh dòng landing thứ hai
create unique index if not exists batch_log_loaded_uq on ctrl.batch_log (batch_id) where status = 'LOADED';
create index if not exists batch_log_hash_ix on ctrl.batch_log (source_table, content_hash) where status = 'LOADED';

-- 3. load_reject: dòng bị loại ngay lúc nạp, không vào landing (INV-T1)
create table if not exists ctrl.load_reject (
    reject_id      bigint generated always as identity primary key,
    log_id         bigint      not null references ctrl.batch_log (log_id),
    batch_id       text        not null,
    source_table   text        not null,
    source_row_no  integer     not null check (source_row_no >= 1),         -- thứ tự dòng dữ liệu trong file, dòng tiêu đề không tính
    reason_code    text        not null,                                    -- ví dụ EVENT_TS_UNPARSEABLE
    detail         text,
    logged_ts      timestamptz not null default now()
);

-- 4. schema_drift: cột mới xuất hiện ở file nguồn so với hợp đồng
create table if not exists ctrl.schema_drift (
    drift_id         bigint generated always as identity primary key,
    log_id           bigint      not null references ctrl.batch_log (log_id),
    source_table     text        not null,
    column_name      text        not null,
    ordinal_position integer     not null,
    landing_type     text        not null default 'text',
    review_status    text        not null default 'PENDING_REVIEW'
                     check (review_status in ('PENDING_REVIEW', 'APPROVED', 'REJECTED')),
    first_seen_ts    timestamptz not null default now(),
    unique (source_table, column_name)                                      -- một cột mới ghi một lần, ở lô thấy đầu tiên
);

-- sổ nạp chỉ thêm dòng. Không dùng REVOKE: khóa ngoại cần quyền khóa dòng của bảng cha, thu quyền UPDATE sẽ làm hỏng INSERT ở bảng con
create or replace function ctrl.f_append_only() returns trigger language plpgsql as $f$
begin
    raise exception 'ctrl.% chỉ thêm dòng, không % được', tg_table_name, lower(tg_op);
end
$f$;
drop trigger if exists trg_append_only on ctrl.batch_log;
create trigger trg_append_only before update or delete on ctrl.batch_log
    for each row execute function ctrl.f_append_only();
drop trigger if exists trg_append_only on ctrl.load_reject;
create trigger trg_append_only before update or delete on ctrl.load_reject
    for each row execute function ctrl.f_append_only();

reset role;
set role finova_dbt;

-- 5. batch_run: sổ chạy. Cửa sổ (lo_ts, hi_ts] của lần sau lấy từ đây
create table if not exists ctrl.batch_run (
    run_id        bigint generated always as identity primary key,
    as_of_date    date        not null,                                     -- ngày D
    cutoff_ts     timestamptz not null,                                     -- cutoff(D): hết ngày D = 00:00 ngày D+1, giờ Việt Nam
    lo_ts         timestamptz not null,                                     -- '-infinity' khi chạy lần đầu hoặc full refresh
    hi_ts         timestamptz not null,
    max_log_id    bigint      not null,                                     -- mọi lô có log_id <= giá trị này thuộc phạm vi lần chạy
    full_refresh  boolean     not null default false,
    status        text        not null check (status in ('RUNNING', 'SUCCESS', 'FAILED', 'BLOCKED_BY_GUARD')),
    error_msg     text,
    started_ts    timestamptz not null default now(),
    finished_ts   timestamptz,
    check (lo_ts <= hi_ts),
    check (not full_refresh or lo_ts = '-infinity'::timestamptz)
);

reset role;
