-- Satellite hồ sơ môi giới từ FLEX, grain: (broker_hk, ingested_ts). Mẫu T-SAT.
-- join_date nằm trong hash_diff: mã cấp lại cho người mới sinh phiên bản mới (DEC-CAP-MG-BROKERKEY).
-- Chỉ mang PII đã che (GT-STG-PII), nên không phải satellite tầng định danh.
{{ dv_load_sat('broker_hk', 'sat_broker_profile_hd', 'stg_flex__broker', [
    'broker_id', 'broker_key', 'join_date', 'leave_date', 'grpid', 'status',
    'email_masked', 'mobile_masked',
]) }}
