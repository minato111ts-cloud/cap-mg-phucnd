-- Dòng bị loại của flex__broker: cùng cột với stg_flex__broker, thêm reason_code (DEC-ELT-REJECT).
-- Truy về landing bằng (batch_id, source_row_no).
select {{ stg_flex__broker_columns() }}, reason_code
from ({{ stg_flex__broker_rows() }}) t
where reason_code is not null
