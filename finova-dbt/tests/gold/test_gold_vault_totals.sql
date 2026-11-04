{{ config(tags = ['gold']) }}

-- Tổng Gold khớp với vault (Bảng 24, tầng Gold), mỗi ngày D:
--   CARE_VS_BRIDGE: số tiểu khoản có phân công ở dim_account_care_daily = số dòng bridge_account_broker;
--   ACCOUNTS: Σ n_accounts của met_broker_daily = số tiểu khoản dim_account_care_daily có broker_key;
--   BOOKNAV: Σ book_nav = Σ NAV ngày D (satellite raw qua con trỏ PIT) của tiểu khoản trong bridge có môi giới
--            trong hồ sơ PIT của D. Vế phải không đọc Gold.
-- Phép thử âm: đếm mọi ứng viên chồng lấn (bỏ rn = 1 ở bridge) hoặc bỏ lọc broker_key -> đỏ.

with care as (
    select as_of_date,
           count(*) filter (where is_assigned) as n_assigned,
           count(*) filter (where broker_key is not null) as n_with_broker
    from {{ ref('dim_account_care_daily') }}
    group by as_of_date
),

bridge as (
    select as_of_date, count(*) as n_bridge
    from {{ ref('bridge_account_broker') }}
    group by as_of_date
),

met as (
    select as_of_date, sum(n_accounts) as n_accounts, sum(book_nav) as book_nav
    from {{ ref('met_broker_daily') }}
    group by as_of_date
),

vault_nav as (
    select b.as_of_date, coalesce(sum(n.nav), 0) as book_nav
    from {{ ref('bridge_account_broker') }} as b
    inner join {{ ref('pit_broker_daily') }} as pb
        on pb.as_of_date = b.as_of_date and pb.broker_hk = b.broker_hk
       and pb.sat_broker_profile_ingested_ts is not null
    inner join {{ ref('pit_account_daily') }} as pa
        on pa.as_of_date = b.as_of_date and pa.account_hk = b.account_hk
    inner join {{ ref('sat_account_nav_daily__flex') }} as n
        on n.account_hk = pa.account_hk and n.business_date = pa.as_of_date
       and n.ingested_ts = pa.sat_account_nav_ingested_ts
    group by b.as_of_date
),

checks as (
    -- xét các ngày đã dựng Gold
    select c.as_of_date, 'CARE_VS_BRIDGE' as problem,
           c.n_assigned::numeric as gold_value, coalesce(b.n_bridge, 0)::numeric as vault_value
    from care as c
    left join bridge as b on b.as_of_date = c.as_of_date
    union all
    select c.as_of_date, 'ACCOUNTS', m.n_accounts, c.n_with_broker
    from care as c
    left join met as m on m.as_of_date = c.as_of_date
    union all
    select m.as_of_date, 'BOOKNAV', m.book_nav, coalesce(v.book_nav, 0)
    from met as m
    left join vault_nav as v on v.as_of_date = m.as_of_date
)

select *
from checks
where gold_value is distinct from vault_value
