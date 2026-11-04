-- Dòng hợp lệ của ref_nav. Phân loại lỗi ở macro stg_flex__nav_rows() (macros/staging/stg_flex__nav.sql),
-- dùng chung với stg_flex__nav__rejected nên hai view luôn cùng cột và không lệch logic.
select {{ stg_flex__nav_columns() }}
from ({{ stg_flex__nav_rows() }}) t
where reason_code is null
