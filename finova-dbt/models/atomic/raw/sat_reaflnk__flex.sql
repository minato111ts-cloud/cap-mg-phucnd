-- Satellite phân công từ FLEX, grain: (reaflnk_hk, ingested_ts). Mẫu T-SAT.
-- Hai trục thời gian: fr_date/to_date là hiệu lực nghiệp vụ, ingested_ts là lúc hệ thống biết.
{{ dv_load_sat('reaflnk_hk', 'sat_reaflnk_hd', 'stg_flex__reaflnk', [
    'autoid', 'broker_id', 'afacctno', 'fr_date', 'to_date', 'status', 'lastchange',
]) }}
