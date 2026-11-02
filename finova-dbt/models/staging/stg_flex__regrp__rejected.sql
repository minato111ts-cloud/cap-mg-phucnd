-- Dòng bị loại của flex__regrp: cùng cột với stg_flex__regrp, thêm reason_code (DEC-ELT-REJECT).
-- Truy về landing bằng (batch_id, source_row_no).
select {{ stg_flex__regrp_columns() }}, reason_code
from ({{ stg_flex__regrp_rows() }}) t
where reason_code is not null
