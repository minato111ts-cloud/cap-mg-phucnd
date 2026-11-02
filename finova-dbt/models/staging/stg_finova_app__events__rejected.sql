-- Dòng bị loại của finova_app__events: cùng cột với stg_finova_app__events, thêm reason_code (DEC-ELT-REJECT).
-- Truy về landing bằng (batch_id, source_row_no).
select {{ stg_finova_app__events_columns() }}, reason_code
from ({{ stg_finova_app__events_rows() }}) t
where reason_code is not null
