{{ config(alias='sat_broker_kpi__manual') }}
-- Chỉ tiêu quý as-of D, grain: broker_hk. File v2 thay v1 kể từ ingested_ts (commit_ts) của nó (TH-NHAPTAY, P-MG-KPI).
{{ asof_latest('sat_broker_kpi__manual', 'broker_hk', sts_model='sts_broker_kpi__manual') }}
