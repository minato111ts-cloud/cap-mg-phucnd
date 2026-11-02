-- Dòng hợp lệ của manual__kpi. Phân loại lỗi ở macro stg_manual__kpi_rows() (macros/staging/stg_manual__kpi.sql),
-- dùng chung với stg_manual__kpi__rejected nên hai view luôn cùng cột và không lệch logic.
select {{ stg_manual__kpi_columns() }}
from ({{ stg_manual__kpi_rows() }}) t
where reason_code is null
