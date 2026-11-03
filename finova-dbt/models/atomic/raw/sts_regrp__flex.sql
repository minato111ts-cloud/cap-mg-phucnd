-- Status tracking đơn vị trong bản chụp đầy đủ flex_regrp, grain: (regrp_hk, ingested_ts). Mẫu T-STS (bản chụp).
-- Khóa vắng khỏi một lô thì DELETED, có lại thì ACTIVE; vắng dòng sts nghĩa là ACTIVE (thay is_deleted, DEC-MG-D4).
{{ dv_load_sts_snapshot('regrp_hk', 'stg_flex__regrp', 'stg_flex__regrp__rejected', 'sat_regrp__flex') }}
