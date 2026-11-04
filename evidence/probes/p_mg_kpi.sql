-- P-MG-KPI: phiên bản chỉ tiêu dùng cho ngày 15/05 (lô của phiên bản PIT trỏ tới) và các dòng bị loại của file chỉ tiêu.
with version as (
    select as_of_date, string_agg(distinct kpi_batch_id || ' (' || kpi_ingested_ts::text || ')', '; ') as v
    from mart.met_broker_daily
    where as_of_date = '2026-05-15' and kpi_batch_id is not null
    group by as_of_date
),
rejected as (
    select string_agg(batch_id || ' ' || reason_code || ' x' || key_count || ' [' || key_sample || ']', '; '
                      order by batch_id, reason_code) as r
    from mart.dq_mg_daily
    where source_table = 'manual_kpi' and handling = 'LOAI' and as_of_date <= '2026-05-15'
)
select v.as_of_date as as_of, 'Phiên bản: ' || v.v || ' | Bị loại: ' || coalesce(r.r, 'không có') as value
from version as v cross join rejected as r;
