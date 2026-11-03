-- Status tracking phân công trong bản chụp đầy đủ flex_reaflnk, grain: (reaflnk_hk, ingested_ts). Mẫu T-STS (bản chụp).
-- Khóa vắng khỏi một lô thì DELETED, có lại thì ACTIVE; vắng dòng sts nghĩa là ACTIVE (thay is_deleted, DEC-MG-D4).
{{ dv_load_sts_snapshot('reaflnk_hk', 'stg_flex__reaflnk', 'stg_flex__reaflnk__rejected', 'sat_reaflnk__flex') }}
