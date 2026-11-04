\encoding UTF8
\set ON_ERROR_STOP on
-- Bảng lỗi tập trung: mọi lỗi và cảnh báo của loader, runner, dbt ghi về một bảng, thay cho thư mục logs/.
-- Mỗi dòng trả lời: lỗi gì (error_code, message), ở đâu (component, step, object_name), thuộc lần chạy / lô nào.
-- Không thay sổ bắt buộc của đề: batch_log, load_reject giữ nguyên; dòng bị loại ở staging vẫn ở view __rejected.
-- Chạy bằng postgres SAU setup/ctrl.sql; chạy lại nhiều lần không lỗi.
-- finova_dbt tạo bảng; finova_loader được cấp INSERT vì loader cũng ghi lỗi vào đây.

set role finova_dbt;

create table if not exists ctrl.error_log (
    error_id     bigint generated always as identity primary key,
    severity     text        not null check (severity in ('ERROR', 'WARN')),
    component    text        not null check (component in ('loader', 'runner', 'dbt')),  -- tầng gặp lỗi
    step         text        not null,              -- bước: check_file, process_batch, t_guard, run_day, tên selector dbt
    object_name  text,                              -- đối tượng: đường dẫn file, bảng nguồn, unique_id của model/test dbt
    run_id       bigint,                            -- ctrl.batch_run.run_id; không khóa ngoại để hai role cùng ghi được
    batch_id     text,                              -- lô liên quan, nếu có
    error_code   text        not null,              -- SHA256_MISMATCH, LOAD_REJECT, BLOCKED_BY_GUARD, MODEL_ERROR, TEST_FAIL, EXCEPTION...
    message      text        not null,              -- toàn văn lỗi (đã che mật khẩu, INV-S4)
    logged_ts    timestamptz not null default now() -- giờ ghi sổ, chỉ để tra cứu, không dùng lọc as-of hay incremental
);

grant insert on ctrl.error_log to finova_loader;

-- chỉ thêm dòng, như batch_log (hàm ctrl.f_append_only tạo ở ctrl.sql)
drop trigger if exists trg_append_only on ctrl.error_log;
create trigger trg_append_only before update or delete on ctrl.error_log
    for each row execute function ctrl.f_append_only();

reset role;
