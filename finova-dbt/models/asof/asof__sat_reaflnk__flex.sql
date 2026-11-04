{{ config(alias='sat_reaflnk__flex') }}
-- Bản REAFLNK as-of D (Bảng 72), grain: reaflnk_hk. Gồm cả phân công chưa tới hoặc đã hết hiệu lực:
-- COVER30 cần biết ai được giao tiểu khoản vào từng ngày trong 30 ngày, theo điều đã biết tại cutoff(D).
{{ asof_latest('sat_reaflnk__flex', 'reaflnk_hk', sts_model='sts_reaflnk__flex') }}
