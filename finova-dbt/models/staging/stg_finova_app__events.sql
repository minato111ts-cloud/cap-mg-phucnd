-- Dòng hợp lệ của finova_app__events. Phân loại lỗi ở macro stg_finova_app__events_rows() (macros/staging/stg_finova_app__events.sql),
-- dùng chung với stg_finova_app__events__rejected nên hai view luôn cùng cột và không lệch logic.
select {{ stg_finova_app__events_columns() }}
from ({{ stg_finova_app__events_rows() }}) t
where reason_code is null
