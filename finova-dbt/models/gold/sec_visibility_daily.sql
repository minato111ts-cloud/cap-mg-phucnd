{{ config(
    grants = {'select': [var('gold_reader_role')]},
    post_hook = [
        "{{ gold_rls_enable() }}",
        "{{ gold_rls_policy(this, 'viewer_id = ' ~ gold_viewer()) }}",
        "{{ gold_rls_enable(ref('dim_account_care_daily')) }}",
        "{{ gold_rls_policy(ref('dim_account_care_daily'),
              'exists (select 1 from ' ~ this ~ ' as v where v.as_of_date = dim_account_care_daily.as_of_date'
              ~ ' and v.account_id = dim_account_care_daily.account_id)') }}",
    ],
) }}

-- Người xem - tiểu khoản được xem tại D, grain: (business_date, viewer_id, account_id). Mẫu T-GOLD-DAY. TH-RLS.
-- Vai trò, phạm vi theo org_roles.csv; loại phạm vi suy từ chính mã, không theo tên vai trò:
--   mã đơn vị: tiểu khoản của môi giới thuộc đơn vị đó hoặc đơn vị bên dưới, theo cây của D;
--   mã môi giới: tiểu khoản do người mang mã đó chăm sóc tại D.
-- Cả hai khớp qua scope_ids của dim_broker_org_daily (mã môi giới và mọi đơn vị trên đường dẫn của D).
-- RLS: người xem chỉ thấy dòng của mình; policy của dim_account_care_daily đọc bảng này (post_hook).
with role_scope as (
    select viewer_id, role, scope
    from {{ ref('ref_org_roles') }}
),

care as (
    select c.account_id, c.broker_key, b.broker_id, b.scope_ids
    from {{ ref('dim_account_care_daily') }} as c
    inner join {{ ref('dim_broker_org_daily') }} as b
        on b.as_of_date = c.as_of_date and b.broker_key = c.broker_key
    where c.as_of_date = {{ asof_var_date() }}
),

final as (
    select
        {{ asof_var_date() }} as business_date,
        {{ asof_var_date() }} as as_of_date,
        {{ asof_var_cutoff() }} as cutoff_ts,
        r.viewer_id,
        c.account_id,
        c.broker_key,
        string_agg(distinct r.role, ',' order by r.role) as roles,
        string_agg(distinct r.scope, ',' order by r.scope) as scopes,
        string_agg(distinct case when r.scope = c.broker_id then 'BROKER' else 'ORG_UNIT' end, ',') as scope_types
    from role_scope as r
    inner join care as c on r.scope = any(c.scope_ids)
    group by r.viewer_id, c.account_id, c.broker_key
)

select * from final
