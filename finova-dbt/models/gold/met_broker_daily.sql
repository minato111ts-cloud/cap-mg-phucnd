{{ config(
    grants = {'select': [var('gold_reader_role')]},
    post_hook = [
        "{{ gold_rls_enable() }}",
        "{{ gold_rls_policy(this,
              'exists (select 1 from ' ~ ref('dim_broker_org_daily') ~ ' as d where d.as_of_date = met_broker_daily.as_of_date'
              ~ ' and d.broker_key = met_broker_daily.broker_key)') }}",
    ],
) }}

-- Chỉ số môi giới tại D, grain: (business_date, broker_key). Mẫu T-GOLD-DAY. Định nghĩa theo Bảng 72, registry ngữ
-- nghĩa ở _gold__models.yml. Mọi môi giới trong hồ sơ as-of D, kể cả người không chăm sóc tiểu khoản nào.
-- Tương tác chỉ tính khi ngày sự kiện nằm trong khoảng làm việc [join_date, leave_date] của người đang mang mã
-- (DEC-CAP-MG-BROKERKEY: mã cấp lại không kéo tương tác của người cũ sang người mới).
-- RLS: người xem thấy chỉ số của môi giới mình thấy ở dim_broker_org_daily.
with broker as (
    select broker_hk, broker_key, broker_id, join_date, leave_date
    from {{ ref('dim_broker_org_daily') }}
    where as_of_date = {{ asof_var_date() }}
),

care as (
    select account_hk, broker_hk, broker_key
    from {{ ref('dim_account_care_daily') }}
    where as_of_date = {{ asof_var_date() }} and broker_key is not null
),

-- NAV của chính ngày D qua con trỏ PIT
nav as (
    select p.account_hk, n.nav
    from {{ ref('pit_account_daily') }} as p
    inner join {{ ref('asof__sat_account_nav_daily__flex') }} as n
        on n.account_hk = p.account_hk
       and n.business_date = p.as_of_date
       and n.ingested_ts = p.sat_account_nav_ingested_ts
    where p.as_of_date = {{ asof_var_date() }}
),

-- sự kiện hợp lệ (đã qua staging) hệ thống biết tại cutoff(D), trong khoảng làm việc của người mang mã,
-- ngày sự kiện từ đầu cửa sổ sớm nhất cần dùng (30 ngày hoặc đầu quý) tới D
event as (
    select b.broker_key, b.broker_hk, e.event_id, e.account_hk, e.event_type, e.event_date
    from broker as b
    inner join {{ ref('asof__nhl_broker_event') }} as e on e.broker_hk = b.broker_hk
    where e.event_date <= {{ asof_var_date() }}
      and e.event_date >= least({{ asof_var_date() }} - 29, date_trunc('quarter', {{ asof_var_date() }})::date)
      and (b.join_date is null or e.event_date >= b.join_date)
      and (b.leave_date is null or e.event_date <= b.leave_date)
),

-- mọi khoảng phân công hệ thống biết tại cutoff(D), để xét "ngày môi giới đang được giao tiểu khoản" (COVER30).
-- materialized: tính view as-of một lần, không lặp lại trong exists
assignment as materialized (
    select l.broker_hk, l.account_hk, s.fr_date, s.to_date
    from {{ ref('asof__sat_reaflnk__flex') }} as s
    inner join {{ ref('asof__link_reaflnk') }} as l on l.reaflnk_hk = s.reaflnk_hk
),

-- tiểu khoản môi giới chăm sóc tại D có tương tác của chính người đó trong 30 ngày lịch kết thúc tại D, vào ngày
-- người đó đang được giao tiểu khoản (tương tác DQ-QUYEN không tính vào độ phủ)
covered as (
    select distinct c.broker_key, c.account_hk
    from care as c
    inner join event as e
        on e.broker_key = c.broker_key
       and e.account_hk = c.account_hk
       and e.event_date >= {{ asof_var_date() }} - 29
    where exists (
        select 1
        from assignment as a
        where a.broker_hk = c.broker_hk
          and a.account_hk = e.account_hk
          and e.event_date between a.fr_date and a.to_date
    )
),

account_agg as (
    select
        c.broker_key,
        count(*) as n_accounts,
        coalesce(sum(n.nav), 0) as book_nav,
        count(*) filter (where n.account_hk is null) as n_accounts_without_nav
    from care as c
    left join nav as n on n.account_hk = c.account_hk
    group by c.broker_key
),

event_agg as (
    select
        broker_key,
        count(distinct event_id) filter (where event_date >= {{ asof_var_date() }} - 29) as interactions_30d,
        count(distinct event_id) filter (where event_type = 'CALL'
                                          and event_date >= date_trunc('quarter', {{ asof_var_date() }})::date)
            as calls_qtd
    from event
    group by broker_key
),

covered_agg as (
    select broker_key, count(*) as cover30_num
    from covered
    group by broker_key
),

-- chỉ tiêu: phiên bản trỏ bởi PIT tại cutoff(D) (TH-NHAPTAY); lô của phiên bản tra ở sổ nạp
kpi as (
    select
        p.broker_hk,
        k.target_calls,
        k.ingested_ts as kpi_ingested_ts,
        bl.batch_id as kpi_batch_id
    from {{ ref('pit_broker_daily') }} as p
    inner join {{ ref('asof__sat_broker_kpi__manual') }} as k
        on k.broker_hk = p.broker_hk and k.ingested_ts = p.sat_broker_kpi_ingested_ts
    left join (
        select distinct on (source_table, ingested_ts) source_table, ingested_ts, batch_id
        from {{ source('ctrl', 'batch_log') }}
        where status = 'LOADED'
        order by source_table, ingested_ts, log_id desc
    ) as bl
        on bl.source_table = split_part(k.record_source, '.', 2) and bl.ingested_ts = k.ingested_ts
    where p.as_of_date = {{ asof_var_date() }}
),

final as (
    select
        {{ asof_var_date() }} as business_date,
        {{ asof_var_date() }} as as_of_date,
        {{ asof_var_cutoff() }} as cutoff_ts,
        b.broker_key,
        b.broker_id,
        b.broker_hk,
        coalesce(a.n_accounts, 0) as n_accounts,
        coalesce(a.book_nav, 0) as book_nav,
        coalesce(a.n_accounts_without_nav, 0) as n_accounts_without_nav,
        coalesce(e.interactions_30d, 0) as interactions_30d,
        coalesce(cv.cover30_num, 0) as cover30_num,
        coalesce(a.n_accounts, 0) as cover30_den,
        coalesce(cv.cover30_num, 0)::numeric / nullif(coalesce(a.n_accounts, 0), 0) as cover30,
        k.target_calls as kpi_target_calls,
        coalesce(e.calls_qtd, 0) as calls_qtd,
        k.kpi_batch_id,
        k.kpi_ingested_ts
    from broker as b
    left join account_agg as a on a.broker_key = b.broker_key
    left join event_agg as e on e.broker_key = b.broker_key
    left join covered_agg as cv on cv.broker_key = b.broker_key
    left join kpi as k on k.broker_hk = b.broker_hk
)

select * from final
