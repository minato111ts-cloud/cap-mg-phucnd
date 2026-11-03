-- Satellite chỉ tiêu quý nhập tay của môi giới, grain: (broker_hk, ingested_ts). Mẫu T-SAT.
-- TH-NHAPTAY: file v2 thay v1 kể từ ingested_ts (commit_ts) của nó; dòng chưa duyệt đã bị loại ở staging.
{{ dv_load_sat('broker_hk', 'sat_broker_kpi_hd', 'stg_manual__kpi', [
    'broker_id', 'target_new_clients', 'target_calls', 'target_aum_bil', 'approver', 'approved_date',
]) }}
