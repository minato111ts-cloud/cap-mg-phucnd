{{ config(
    grants = {'select': [var('gold_reader_role')]},
    post_hook = [
        "{{ gold_viewer_scopes_function() }}",
        "{{ gold_rls_enable() }}",
        "{{ gold_rls_policy(this, 'scope_ids && ' ~ this.schema ~ '.viewer_scopes()') }}",
    ],
) }}
-- depends_on: {{ ref('ref_org_roles') }}

-- Môi giới và vị trí trong cây đơn vị của ngày D, grain: (business_date, broker_key). Mẫu T-GOLD-DAY.
-- Hồ sơ lấy qua con trỏ PIT (pit_broker_daily); đường dẫn cây theo bridge_regrp_ancestor của D (TH-TAICAUTRUC).
-- broker_key = BROKERID:JOINDATE của người đang mang mã tại D (DEC-CAP-MG-BROKERKEY).
-- Chi nhánh là đơn vị ngay dưới gốc trên đường dẫn, không theo grplevel: nhánh mồ côi có số liệu nằm dưới UNKNOWN
-- (DEC-CAP-MG-ORPHAN). Môi giới thuộc đơn vị không có trong cây của D: đường dẫn NULL, is_in_tree = false.
-- RLS: người xem thấy môi giới có scope_ids (mã môi giới và mọi đơn vị trên đường dẫn) chứa phạm vi của mình.
with pit as (
    select broker_hk, sat_broker_profile_ingested_ts
    from {{ ref('pit_broker_daily') }}
    where as_of_date = {{ asof_var_date() }}
      and sat_broker_profile_ingested_ts is not null
),

profile as (
    select b.*
    from pit as p
    inner join {{ ref('asof__sat_broker_profile__flex') }} as b
        on b.broker_hk = p.broker_hk and b.ingested_ts = p.sat_broker_profile_ingested_ts
),

unit as (
    select regrp_hk, grpid
    from {{ ref('asof__sat_regrp__flex') }}
),

-- đường dẫn từ gốc xuống đơn vị: cấp trên xếp theo depth giảm dần
org_path as (
    select
        a.regrp_hk,
        array_agg(
            case when a.ancestor_regrp_hk = {{ bv_regrp_unknown_hk() }} then {{ bv_regrp_unknown_bk() }} else u.grpid end
            order by a.depth desc
        ) as path_ids,
        bool_or(a.is_orphan_branch) as is_orphan_branch
    from {{ ref('bridge_regrp_ancestor') }} as a
    left join unit as u on u.regrp_hk = a.ancestor_regrp_hk
    where a.as_of_date = {{ asof_var_date() }}
    group by a.regrp_hk
),

final as (
    select
        {{ asof_var_date() }} as business_date,
        {{ asof_var_date() }} as as_of_date,
        {{ asof_var_cutoff() }} as cutoff_ts,
        coalesce(b.broker_key, b.broker_id || ':UNKNOWN') as broker_key,
        b.broker_id,
        b.broker_hk,
        b.grpid as grp_id,
        op.path_ids[2] as branch_id,
        array_to_string(op.path_ids, ' > ') as org_path,
        op.path_ids is not null as is_in_tree,
        coalesce(op.is_orphan_branch, false) as is_orphan_branch,
        b.join_date,
        b.leave_date,
        b.status as broker_status,
        -- DEC-CAP-MG-GAP: đã nghỉ khi STATUS = C hoặc D sau LEAVEDATE
        case
            when b.join_date > {{ asof_var_date() }} then 'NOT_STARTED'
            when b.status = 'C' or b.leave_date < {{ asof_var_date() }} then 'LEFT'
            else 'ACTIVE'
        end as work_status,
        coalesce(op.path_ids, '{}'::text[]) || b.broker_id as scope_ids
    from profile as b
    left join unit as u on u.grpid = b.grpid
    left join org_path as op on op.regrp_hk = u.regrp_hk
)

select * from final
