-- Status tracking dòng chỉ tiêu của môi giới trong file manual_kpi (bản chụp đầy đủ), grain: (broker_hk, ingested_ts).
-- Môi giới vắng khỏi phiên bản file sau thì DELETED: chỉ tiêu của bản trước hết hiệu lực từ ingested_ts đó.
{{ dv_load_sts_snapshot('broker_hk', 'stg_manual__kpi', 'stg_manual__kpi__rejected', 'sat_broker_kpi__manual') }}
