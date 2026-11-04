-- Dòng bị loại của ref_nav: cùng cột với stg_flex__nav, thêm reason_code (DEC-ELT-REJECT).
-- Truy về landing bằng (batch_id, source_row_no).
select {{ stg_flex__nav_columns() }}, reason_code
from ({{ stg_flex__nav_rows() }}) t
where reason_code is not null
