{{ config(tags = ['staging']) }}

-- GT-STG-RECON theo từng batch_id (Bảng 85): ctrl.batch_log.rows_loaded = số dòng landing
-- = số dòng hợp lệ + số dòng bị loại. Đủ ba vế để bắt cả lỗi loader (sổ lệch landing) lẫn lỗi staging
-- (dòng biến mất, không vào view nào).
-- Phép thử âm: thêm `and source_row_no <> 1` vào where của một view staging -> test đỏ ở mọi lô của bảng đó.

{% set tables = [
    ('flex_regrp', 'stg_flex__regrp'),
    ('flex_broker', 'stg_flex__broker'),
    ('flex_reaflnk', 'stg_flex__reaflnk'),
    ('ref_nav', 'stg_ref__nav'),
    ('finova_app_events', 'stg_finova_app__events'),
    ('manual_kpi', 'stg_manual__kpi'),
] %}

with landing_counts as (
    {% for src, stg in tables %}
    select '{{ src }}' as source_table, batch_id, count(*) as rows_landing
    from {{ source('landing', src) }} group by batch_id
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
),

staging_counts as (
    {% for src, stg in tables %}
    select '{{ src }}' as source_table, batch_id, sum(is_valid) as rows_valid, sum(1 - is_valid) as rows_rejected
    from (
        select batch_id, 1 as is_valid from {{ ref(stg) }}
        union all
        select batch_id, 0 from {{ ref(stg ~ '__rejected') }}
    ) s group by batch_id
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
),

ctrl_counts as (
    select source_table, batch_id, rows_loaded
    from {{ source('ctrl', 'batch_log') }}
    where status = 'LOADED'
)

select
    coalesce(c.source_table, l.source_table, s.source_table) as source_table,
    coalesce(c.batch_id, l.batch_id, s.batch_id) as batch_id,
    c.rows_loaded, l.rows_landing, s.rows_valid, s.rows_rejected
from ctrl_counts c
full outer join landing_counts l on l.source_table = c.source_table and l.batch_id = c.batch_id
full outer join staging_counts s
    on s.source_table = coalesce(c.source_table, l.source_table)
   and s.batch_id = coalesce(c.batch_id, l.batch_id)
where coalesce(c.rows_loaded, -1) <> coalesce(l.rows_landing, 0)
   or coalesce(l.rows_landing, 0) <> coalesce(s.rows_valid, 0) + coalesce(s.rows_rejected, 0)
