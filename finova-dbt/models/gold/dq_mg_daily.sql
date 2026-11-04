-- Báo cáo chất lượng theo lô (D-DQ, Phụ lục C, Bảng 75), grain: (as_of_date, batch_id, source_table, reason_code).
-- Mẫu T-GOLD-DAY. Ngày D gồm các lô có ingested_ts trong (cutoff(ngày giao dịch liền trước), cutoff(D)], nên lô của
-- ngày nghỉ (sự kiện cuối tuần) vào ngày giao dịch kế tiếp. Lô không nạp (SKIPPED_DUP, REJECTED_BATCH) không có
-- ingested_ts: xếp theo business_date trong (ngày giao dịch liền trước, D].
-- Mỗi lô: rows_landing (= batch_log.rows_loaded), rows_valid, rows_rejected đếm từ view staging hợp lệ và __rejected
-- (rows_landing = rows_valid + rows_rejected, GT-STG-RECON). Mỗi lỗi một dòng: reason_code của __rejected, hoặc mã
-- cờ không loại dòng (FUTURE_TS_FIXED, PARENT_MISSING, EVENT_NOT_ASSIGNED, ASSIGNMENT_OVERLAP, KEY_REUSED), hoặc
-- reason_code của batch_log với lô
-- không nạp. Lô không có lỗi: một dòng reason_code NULL. Mã DQ, hướng xử lý, test theo seed ref_dq_reason.
{%- set sources = [
    ('flex_regrp', 'stg_flex__regrp', 'grpid'),
    ('flex_broker', 'stg_flex__broker', 'broker_id'),
    ('flex_reaflnk', 'stg_flex__reaflnk', 'autoid'),
    ('ref_nav', 'stg_ref__nav', 'afacctno'),
    ('finova_app_events', 'stg_finova_app__events', 'event_id'),
    ('manual_kpi', 'stg_manual__kpi', 'broker_id'),
] %}

with assignment as materialized (
    -- mọi khoảng phân công hệ thống biết tại cutoff(D), tính view as-of một lần
    select l.broker_hk, l.account_hk, s.fr_date, s.to_date
    from {{ ref('asof__sat_reaflnk__flex') }} as s
    inner join {{ ref('asof__link_reaflnk') }} as l on l.reaflnk_hk = s.reaflnk_hk
),

window_ts as (
    select
        {{ gold_prev_trading_day() }} as prev_day,
        coalesce(({{ gold_prev_trading_day() }} + 1)::timestamp at time zone 'Asia/Ho_Chi_Minh', '-infinity'::timestamptz)
            as lo_ts,
        {{ asof_var_cutoff() }} as hi_ts
),

-- dòng sổ cuối của mỗi lô (KT-22: lô từng SKIPPED_DUP rồi được nạp lại có hai dòng sổ)
last_log as (
    select distinct on (batch_id) batch_id, source_table, business_date, ingested_ts, status, reason_code,
           coalesce(rows_loaded, 0) as rows_landing
    from {{ source('ctrl', 'batch_log') }}
    order by batch_id, log_id desc
),

batch as (
    select l.*
    from last_log as l
    cross join window_ts as w
    where (l.ingested_ts is not null and l.ingested_ts > w.lo_ts and l.ingested_ts <= w.hi_ts)
       or (l.ingested_ts is null and (w.prev_day is null or l.business_date > w.prev_day)
           and l.business_date <= {{ asof_var_date() }})
),

valid_count as (
    {%- for src, stg, key in sources %}
    select '{{ src }}' as source_table, batch_id, count(*) as n
    from {{ ref(stg) }}
    group by batch_id
    {%- if not loop.last %}
    union all
    {%- endif %}
    {%- endfor %}
),

-- lỗi theo dòng: khóa mẫu là khóa nghiệp vụ, khóa rỗng thì số dòng nguồn
issue as (
    {%- for src, stg, key in sources %}
    select '{{ src }}' as source_table, batch_id, reason_code,
           coalesce({{ key }}::text, 'row_' || source_row_no) as issue_key, true as is_rejected
    from {{ ref(stg ~ '__rejected') }}
    union all
    {%- endfor %}
    -- DQ-TUONGLAI: sửa bằng server_ts, dòng vẫn hợp lệ
    select 'finova_app_events', batch_id, 'FUTURE_TS_FIXED', event_id, false
    from {{ ref('stg_finova_app__events') }}
    where is_future_ts_fixed
    union all
    -- DQ-MOCOI: cha không có trong cùng bản chụp, dòng vẫn hợp lệ
    select 'flex_regrp', r.batch_id, 'PARENT_MISSING', r.grpid, false
    from {{ ref('stg_flex__regrp') }} as r
    where r.parentid is not null
      and not exists (
          select 1 from {{ ref('stg_flex__regrp') }} as p
          where p.batch_id = r.batch_id and p.grpid = r.parentid
      )
    union all
    -- DQ-CHONGLAN: trong cùng bản chụp, một tiểu khoản có hai phân công của hai môi giới với khoảng hiệu lực giao nhau
    select distinct 'flex_reaflnk', a.batch_id, 'ASSIGNMENT_OVERLAP', a.afacctno, false
    from {{ ref('stg_flex__reaflnk') }} as a
    inner join {{ ref('stg_flex__reaflnk') }} as b
        on b.batch_id = a.batch_id and b.account_hk = a.account_hk and b.broker_hk <> a.broker_hk
       and a.fr_date <= b.to_date and b.fr_date <= a.to_date
    union all
    -- DQ-KHOA-TAISUDUNG: mã môi giới mang JOINDATE khác phiên bản trước của chính mã đó (người khác nhận mã)
    select 'flex_broker', batch_id, 'KEY_REUSED', broker_id, false
    from (
        select batch_id, broker_id, join_date,
               lag(join_date) over (partition by broker_id order by ingested_ts, batch_id) as prev_join_date,
               row_number() over (partition by broker_id order by ingested_ts, batch_id) as rn
        from {{ ref('stg_flex__broker') }}
    ) as v
    where rn > 1 and join_date is distinct from prev_join_date
    union all
    -- DQ-QUYEN: không có phân công của môi giới cho tiểu khoản vào ngày sự kiện, theo phân công hệ thống biết tại cutoff(D)
    select 'finova_app_events', e.batch_id, 'EVENT_NOT_ASSIGNED', e.event_id, false
    from {{ ref('stg_finova_app__events') }} as e
    where not exists (
        select 1
        from assignment as a
        where a.broker_hk = e.broker_hk
          and a.account_hk = e.account_hk
          and e.event_date between a.fr_date and a.to_date
    )
),

rejected_count as (
    select source_table, batch_id, count(*) as n
    from issue
    where is_rejected
    group by source_table, batch_id
),

issue_agg as (
    select
        source_table,
        batch_id,
        reason_code,
        count(distinct issue_key) as key_count,
        (array_agg(distinct issue_key order by issue_key))[1:5] as key_sample
    from issue
    group by source_table, batch_id, reason_code
),

batch_row as (
    select
        b.batch_id,
        b.source_table,
        b.business_date,
        b.rows_landing,
        coalesce(v.n, 0) as rows_valid,
        coalesce(r.n, 0) as rows_rejected,
        case when b.status = 'LOADED' then i.reason_code else b.reason_code end as reason_code,
        coalesce(i.key_count, 0) as key_count,
        array_to_string(i.key_sample, ';') as key_sample
    from batch as b
    left join valid_count as v on v.source_table = b.source_table and v.batch_id = b.batch_id
    left join rejected_count as r on r.source_table = b.source_table and r.batch_id = b.batch_id
    left join issue_agg as i
        on b.status = 'LOADED' and i.source_table = b.source_table and i.batch_id = b.batch_id
),

final as (
    select
        b.business_date,
        {{ asof_var_date() }} as as_of_date,
        {{ asof_var_cutoff() }} as cutoff_ts,
        b.batch_id,
        b.source_table,
        b.rows_landing,
        b.rows_valid,
        b.rows_rejected,
        nullif(m.defect_code, '') as defect_code,
        b.reason_code,
        b.key_count,
        b.key_sample,
        nullif(m.handling, '') as handling,
        m.test_id
    from batch_row as b
    left join {{ ref('ref_dq_reason') }} as m on m.reason_code = b.reason_code
)

select * from final
