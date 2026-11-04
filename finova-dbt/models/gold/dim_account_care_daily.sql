{{ config(
    grants = {'select': [var('gold_reader_role')]},
    post_hook = ["{{ gold_rls_enable() }}"],
) }}

-- Tiểu khoản và môi giới chăm sóc tại D, grain: (business_date, account_id). Mẫu T-GOLD-DAY.
-- Tập tiểu khoản: mọi tiểu khoản hệ thống biết tại cutoff(D), qua phân công (REAFLNK) hoặc NAV của D.
-- Môi giới chăm sóc theo bridge_account_broker (phân công hiệu lực tại D, chồng lấn theo DEC-CAP-MG-OVERLAP).
-- broker_key là người đang mang mã tại D; người đó đã nghỉ thì giữ, có cờ (DEC-CAP-MG-GAP, TH-NGHIVIEC).
-- care_basis: NO_ASSIGNMENT, hoặc REAFLNK kèm +DEC-CAP-MG-OVERLAP, +DEC-CAP-MG-GAP khi áp quyết định đó.
-- RLS: bật ở đây (chưa có policy thì role đọc không thấy gì); policy theo sec_visibility_daily do post_hook của
-- sec_visibility_daily tạo, vì bảng đó dựng sau bảng này.
with assigned_account as (
    select l.account_hk, s.afacctno as account_id
    from {{ ref('asof__sat_reaflnk__flex') }} as s
    inner join {{ ref('asof__link_reaflnk') }} as l on l.reaflnk_hk = s.reaflnk_hk
),

nav_account as (
    select n.account_hk, n.afacctno as account_id
    from {{ ref('asof__sat_account_nav_daily__flex') }} as n
    where n.business_date = {{ asof_var_date() }}
),

account as (
    select distinct on (account_hk) account_hk, account_id
    from (
        select * from assigned_account
        union all
        select * from nav_account
    ) as a
    order by account_hk, account_id
),

care as (
    select b.account_hk, b.broker_hk, b.reaflnk_hk, b.is_overlap, e.autoid, e.broker_id, e.fr_date, e.to_date
    from {{ ref('bridge_account_broker') }} as b
    inner join {{ ref('asof__esat_reaflnk__flex') }} as e on e.reaflnk_hk = b.reaflnk_hk
    where b.as_of_date = {{ asof_var_date() }}
),

broker as (
    select broker_hk, broker_key, work_status
    from {{ ref('dim_broker_org_daily') }}
    where as_of_date = {{ asof_var_date() }}
),

joined as (
    select
        a.account_id,
        a.account_hk,
        c.broker_id,
        br.broker_key,
        c.broker_hk,
        c.autoid as reaflnk_autoid,
        c.fr_date,
        c.to_date,
        c.broker_hk is not null as is_assigned,
        coalesce(c.is_overlap, false) as is_overlap,
        -- người mang mã không ở trạng thái đang làm tại D, hoặc mã không còn trong hồ sơ as-of D
        c.broker_hk is not null and br.work_status is distinct from 'ACTIVE' as is_carer_inactive
    from account as a
    left join care as c on c.account_hk = a.account_hk
    left join broker as br on br.broker_hk = c.broker_hk
),

final as (
    select
        {{ asof_var_date() }} as business_date,
        {{ asof_var_date() }} as as_of_date,
        {{ asof_var_cutoff() }} as cutoff_ts,
        account_id,
        account_hk,
        broker_id,
        broker_key,
        broker_hk,
        reaflnk_autoid,
        fr_date,
        to_date,
        case
            when not is_assigned then 'NO_ASSIGNMENT'
            else concat_ws('+', 'REAFLNK',
                           case when is_overlap then 'DEC-CAP-MG-OVERLAP' end,
                           case when is_carer_inactive then 'DEC-CAP-MG-GAP' end)
        end as care_basis,
        is_assigned,
        is_overlap,
        is_carer_inactive
    from joined
)

select * from final
