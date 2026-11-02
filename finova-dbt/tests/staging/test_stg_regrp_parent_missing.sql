{{ config(tags = ['staging'], severity = 'warn') }}

-- DQ-MOCOI (CANHBAO, Bảng 67): đơn vị trỏ tới đơn vị cha không có trong cùng bản chụp.
-- Dòng vẫn nhận (raw vault giữ mọi dòng dựng được khóa); test warn đếm để báo cáo D-DQ.
-- Phép thử âm: đổi severity sang error -> build đỏ ở các lô có G7 -> CN9.

select r.batch_id, r.grpid, r.parentid
from {{ ref('stg_flex__regrp') }} r
where r.parentid is not null
  and not exists (
      select 1
      from (
          select batch_id, grpid from {{ ref('stg_flex__regrp') }}
          union all
          select batch_id, grpid from {{ ref('stg_flex__regrp__rejected') }}
      ) p
      where p.batch_id = r.batch_id and p.grpid = r.parentid
  )
