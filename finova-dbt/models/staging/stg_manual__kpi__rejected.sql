-- Dòng bị loại của manual__kpi: cùng cột với stg_manual__kpi, thêm reason_code (DEC-ELT-REJECT).
-- Truy về landing bằng (batch_id, source_row_no).
select {{ stg_manual__kpi_columns() }}, reason_code
from ({{ stg_manual__kpi_rows() }}) t
where reason_code is not null
