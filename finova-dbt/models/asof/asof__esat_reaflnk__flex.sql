{{ config(alias='esat_reaflnk__flex') }}
-- Phân công hiệu lực tại D, grain: reaflnk_hk. Bảng 72: FRDATE ≤ D ≤ TODATE trong bản REAFLNK as-of D;
-- quy tắc esat có thời hiệu ở Bảng 88. Không lọc STATUS (Bảng 72 không có điều kiện này).
-- Chưa phân xử chồng lấn: một tiểu khoản có thể có hai dòng (DQ-CHONGLAN); bridge ở BV chọn theo DEC-CAP-MG-OVERLAP.
select l.link_reaflnk_hk, l.broker_hk, l.account_hk, s.*
from {{ ref('asof__sat_reaflnk__flex') }} s
join {{ ref('asof__link_reaflnk') }} l on l.reaflnk_hk = s.reaflnk_hk
where s.fr_date <= (select asof.as_of_date())
  and s.to_date >= (select asof.as_of_date())
