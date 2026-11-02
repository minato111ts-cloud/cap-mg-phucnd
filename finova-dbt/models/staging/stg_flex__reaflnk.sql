-- Dòng hợp lệ của flex__reaflnk. Phân loại lỗi ở macro stg_flex__reaflnk_rows() (macros/staging/stg_flex__reaflnk.sql),
-- dùng chung với stg_flex__reaflnk__rejected nên hai view luôn cùng cột và không lệch logic.
select {{ stg_flex__reaflnk_columns() }}
from ({{ stg_flex__reaflnk_rows() }}) t
where reason_code is null
