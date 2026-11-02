-- Dòng hợp lệ của ref__nav. Phân loại lỗi ở macro stg_ref__nav_rows() (macros/staging/stg_ref__nav.sql),
-- dùng chung với stg_ref__nav__rejected nên hai view luôn cùng cột và không lệch logic.
select {{ stg_ref__nav_columns() }}
from ({{ stg_ref__nav_rows() }}) t
where reason_code is null
