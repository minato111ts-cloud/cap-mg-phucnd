{{ config(tags = ['gold']) }}

-- DEC-CAP-MG-BROKERKEY, DQ-KHOA-TAISUDUNG, mỗi ngày D:
--   KPI_INHERITED: chỉ tiêu ở met_broker_daily có ngày duyệt (satellite raw của phiên bản kpi_ingested_ts) nằm ngoài
--                  [join_date, leave_date] của người mang mã ở dim_broker_org_daily (người mới nhận chỉ tiêu người cũ);
--   KPI_UNFLAGGED: PIT trỏ tới chỉ tiêu mà met_broker_daily không áp, nhưng không có cờ KPI_NOT_FOR_HOLDER của mã đó
--                  ở dq_mg_daily tại ngày nào tới D (chỉ tiêu bị bỏ mà không ai biết). key_sample giữ tối đa 5 mã
--                  mỗi lô: một lô có hơn 5 mã bị chặn sẽ đỏ nhầm, khi đó xem lại cột key_count.
-- Vế phải đọc raw vault, không qua macro gold_in_tenure. Gói đề không có ca bị chặn, nên trên gói đề test này chỉ
-- chặn hồi quy; ca chặn được thử ở ut_met_kpi_not_for_new_holder, ut_dq_kpi_not_for_holder_on_reuse_batch.
-- Phép thử âm: bỏ điều kiện khoảng làm việc ở CTE kpi của met_broker_daily -> đỏ khi có ca.

with met as (
    select m.as_of_date, m.broker_key, m.broker_id, m.broker_hk, m.kpi_target_calls, m.kpi_ingested_ts,
           d.join_date, d.leave_date
    from {{ ref('met_broker_daily') }} as m
    inner join {{ ref('dim_broker_org_daily') }} as d
        on d.as_of_date = m.as_of_date and d.broker_key = m.broker_key
),

inherited as (
    select m.as_of_date, m.broker_key, 'KPI_INHERITED' as check_code
    from met as m
    inner join {{ ref('sat_broker_kpi__manual') }} as k
        on k.broker_hk = m.broker_hk and k.ingested_ts = m.kpi_ingested_ts
    where m.kpi_target_calls is not null
      and (k.approved_date < m.join_date or k.approved_date > m.leave_date)
),

unflagged as (
    select m.as_of_date, m.broker_key, 'KPI_UNFLAGGED' as check_code
    from met as m
    inner join {{ ref('pit_broker_daily') }} as p
        on p.as_of_date = m.as_of_date and p.broker_hk = m.broker_hk
    where p.sat_broker_kpi_ingested_ts is not null
      and m.kpi_target_calls is null
      and not exists (
          select 1 from {{ ref('dq_mg_daily') }} as q
          where q.reason_code = 'KPI_NOT_FOR_HOLDER' and q.as_of_date <= m.as_of_date
            and m.broker_id = any(string_to_array(q.key_sample, ';'))
      )
)

select * from inherited
union all
select * from unflagged
