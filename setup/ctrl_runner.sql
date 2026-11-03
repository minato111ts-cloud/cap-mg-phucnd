\encoding UTF8
\set ON_ERROR_STOP on
-- Bảng ctrl bổ sung cho runner CAP-MG. Mẫu ctrl.sql của gói đề cho phép thêm; file đó giữ nguyên.
--   guard_block, guard_resolution: lô T-GUARD chặn và cách người vận hành xử lý (RV-10)
--   reject_count: số dòng bị loại theo (batch_id, reason_code) của mỗi lần chạy (DEC-ELT-REJECT, RV-11)
-- Chạy bằng postgres SAU setup/ctrl.sql; chạy lại nhiều lần không lỗi. finova_dbt tạo và ghi cả ba bảng.

-- khóa ngoại từ bảng của finova_dbt tới sổ nạp của finova_loader
set role finova_loader;
grant references (log_id) on ctrl.batch_log to finova_dbt;
reset role;

set role finova_dbt;

-- 1. guard_block: mỗi lô T-GUARD bắt được ở một lần chạy BLOCKED_BY_GUARD ghi một dòng.
--    Chạy lại khi chưa xử lý thì lô bị ghi lại dưới run_id mới; ctrl.v_guard_open gộp theo lô.
create table if not exists ctrl.guard_block (
    block_id         bigint generated always as identity primary key,
    run_id           bigint      not null references ctrl.batch_run (run_id),   -- lần chạy bị chặn
    log_id           bigint      not null references ctrl.batch_log (log_id),   -- dòng sổ nạp của lô bị chặn
    batch_id         text        not null,
    source_table     text        not null,
    business_date    date,
    ingested_ts      timestamptz not null,                                      -- giờ của lô: <= lo_ts
    lo_ts            timestamptz not null,                                      -- cận dưới cửa sổ của lần chạy bị chặn
    prev_max_log_id  bigint      not null,                                      -- max_log_id của lần SUCCESS trước: log_id lớn hơn
    rows_loaded      integer     not null,                                      -- số dòng landing của lô
    logged_ts        timestamptz not null default now(),                        -- giờ ghi sổ, chỉ để tra cứu
    unique (run_id, log_id),
    check (ingested_ts <= lo_ts and log_id > prev_max_log_id)
);

-- 2. guard_resolution: mỗi lô bị chặn được xử lý đúng một lần.
--    FULL_REFRESH: runner tự ghi khi một lần full refresh SUCCESS có max_log_id phủ lô; lô đã vào vault.
--    ACCEPTED: người vận hành cho chạy tiếp mà không đưa lô vào vault; bắt buộc ghi lý do.
--              Lô vào vault ở lần full refresh kế tiếp, với ingested_ts cũ của nó.
create table if not exists ctrl.guard_resolution (
    resolution_id    bigint generated always as identity primary key,
    log_id           bigint      not null unique references ctrl.batch_log (log_id),
    action           text        not null check (action in ('FULL_REFRESH', 'ACCEPTED')),
    resolved_run_id  bigint      references ctrl.batch_run (run_id),            -- lần full refresh đã đưa lô vào vault
    resolved_by      text        not null,                                      -- người vận hành, hoặc 'runner'
    note             text,
    logged_ts        timestamptz not null default now(),
    check (action <> 'FULL_REFRESH' or resolved_run_id is not null),
    check (action <> 'ACCEPTED' or length(btrim(coalesce(note, ''))) > 0)
);

-- 3. reject_count: số dòng của view __rejected trong cửa sổ của lần chạy, theo lô và reason_code.
--    Nạp theo ngày thì mỗi lô được đếm ở đúng một lần SUCCESS; full refresh đếm lại mọi lô.
create table if not exists ctrl.reject_count (
    run_id           bigint      not null references ctrl.batch_run (run_id),
    batch_id         text        not null,
    source_table     text        not null,                                      -- bảng landing của lô
    staging_view     text        not null,                                      -- ví dụ stg_flex__regrp__rejected
    reason_code      text        not null,
    row_count        integer     not null check (row_count > 0),
    logged_ts        timestamptz not null default now(),
    primary key (run_id, batch_id, staging_view, reason_code)
);

-- sổ chỉ thêm dòng, như batch_log (hàm ctrl.f_append_only tạo ở ctrl.sql)
drop trigger if exists trg_append_only on ctrl.guard_block;
create trigger trg_append_only before update or delete on ctrl.guard_block
    for each row execute function ctrl.f_append_only();
drop trigger if exists trg_append_only on ctrl.guard_resolution;
create trigger trg_append_only before update or delete on ctrl.guard_resolution
    for each row execute function ctrl.f_append_only();
drop trigger if exists trg_append_only on ctrl.reject_count;
create trigger trg_append_only before update or delete on ctrl.reject_count
    for each row execute function ctrl.f_append_only();

-- 4. v_guard_open: việc của người vận hành, mỗi lô bị chặn chưa xử lý một dòng
create or replace view ctrl.v_guard_open as
select b.log_id,
       b.batch_id,
       b.source_table,
       b.business_date,
       b.ingested_ts,
       b.rows_loaded,
       min(b.lo_ts)     as first_lo_ts,
       count(*)         as blocked_runs,
       min(b.run_id)    as first_run_id,
       max(b.run_id)    as last_run_id,
       max(r.as_of_date) as last_as_of_date
from ctrl.guard_block b
join ctrl.batch_run r on r.run_id = b.run_id
where not exists (select 1 from ctrl.guard_resolution x where x.log_id = b.log_id)
group by b.log_id, b.batch_id, b.source_table, b.business_date, b.ingested_ts, b.rows_loaded;

reset role;
