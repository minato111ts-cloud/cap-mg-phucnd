-- Dòng hợp lệ của flex__regrp. Phân loại lỗi ở macro stg_flex__regrp_rows() (macros/staging/stg_flex__regrp.sql),
-- dùng chung với stg_flex__regrp__rejected nên hai view luôn cùng cột và không lệch logic.
select {{ stg_flex__regrp_columns() }}
from ({{ stg_flex__regrp_rows() }}) t
where reason_code is null
