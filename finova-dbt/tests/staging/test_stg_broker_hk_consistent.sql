{{ config(tags = ['staging']) }}

-- DEC-CAP-MG-BROKERKEY (PA A): mọi staging mang mã môi giới phải sinh cùng broker_hk cho cùng mã,
-- nếu không link ở raw vault sẽ trỏ tới khóa không có trong hub (GT-LNK-PARENT).
-- Phép thử âm: đổi broker_hk của một view về dv_hash([mã]) không có 'FLEX' thì test đỏ.

with hub_side as (
    select distinct bk_broker, broker_hk
    from {{ ref('stg_flex__broker') }}
),

link_side as (
    select 'stg_flex__reaflnk' as model_name, bk_broker, broker_hk from {{ ref('stg_flex__reaflnk') }}
    union all
    select 'stg_finova_app__events', bk_broker, broker_hk from {{ ref('stg_finova_app__events') }}
    union all
    select 'stg_manual__kpi', bk_broker, broker_hk from {{ ref('stg_manual__kpi') }}
)

select l.model_name, l.bk_broker, l.broker_hk as link_broker_hk, h.broker_hk as hub_broker_hk
from link_side l
join hub_side h on h.bk_broker = l.bk_broker
where l.broker_hk <> h.broker_hk
