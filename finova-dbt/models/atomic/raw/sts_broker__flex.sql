-- Status tracking môi giới trong bản chụp đầy đủ flex_broker, grain: (broker_hk, ingested_ts). Mẫu T-STS (bản chụp).
-- Khóa vắng khỏi một lô thì DELETED, có lại thì ACTIVE; vắng dòng sts nghĩa là ACTIVE (thay is_deleted, DEC-MG-D4).
{{ dv_load_sts_snapshot('broker_hk', 'stg_flex__broker', 'stg_flex__broker__rejected', 'sat_broker_profile__flex') }}
