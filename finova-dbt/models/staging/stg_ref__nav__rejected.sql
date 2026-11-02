-- Dòng bị loại của ref__nav: cùng cột với stg_ref__nav, thêm reason_code (DEC-ELT-REJECT).
-- Truy về landing bằng (batch_id, source_row_no).
select {{ stg_ref__nav_columns() }}, reason_code
from ({{ stg_ref__nav_rows() }}) t
where reason_code is not null
