-- Dòng hợp lệ của flex__broker. Phân loại lỗi ở macro stg_flex__broker_rows() (macros/staging/stg_flex__broker.sql),
-- dùng chung với stg_flex__broker__rejected nên hai view luôn cùng cột và không lệch logic.
select {{ stg_flex__broker_columns() }}
from ({{ stg_flex__broker_rows() }}) t
where reason_code is null
