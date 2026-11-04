{{ config(tags = ['gold']) }}

-- D-DQ khớp với ctrl.batch_log và __rejected (Bảng 25):
--   RECON: lô LOADED có rows_landing = rows_valid + rows_rejected (GT-STG-RECON ở Gold);
--   LANDING: rows_landing = batch_log.rows_loaded của dòng sổ cuối của lô;
--   WRONG_DAY / MISSING_BATCH: mỗi lô thuộc đúng một ngày D, là ngày giao dịch đầu tiên có cutoff(D) >= ingested_ts
--   (lô không nạp, không có ingested_ts: ngày giao dịch đầu tiên >= business_date). Lô có mặt thì chỉ ở ngày đó; ngày
--   đó đã dựng thì lô phải có mặt. Lô T-GUARD đã chặn mà chưa được full refresh xử lý nằm ngoài mọi cửa sổ theo ngày
--   cho tới lần full refresh (RV-10), nên được phép vắng.
-- Phép thử âm: bỏ một view __rejected khỏi danh sách nguồn của dq_mg_daily -> RECON đỏ.

with dq as (
    select distinct as_of_date, batch_id, source_table, rows_landing, rows_valid, rows_rejected
    from {{ ref('dq_mg_daily') }}
),

built_day as (
    select distinct as_of_date from dq
),

trading_day as (
    select calendar_date as d, ((calendar_date + 1)::timestamp at time zone 'Asia/Ho_Chi_Minh') as cutoff_ts
    from {{ ref('ref_calendar') }}
    where is_trading_day = 1
),

last_log as (
    select distinct on (bl.batch_id) bl.batch_id, bl.status, coalesce(bl.rows_loaded, 0) as rows_loaded, bl.ingested_ts,
           bl.business_date,
           exists (select 1 from {{ source('ctrl', 'guard_block') }} as g where g.log_id = bl.log_id)
           and not exists (select 1 from {{ source('ctrl', 'guard_resolution') }} as r
                           where r.log_id = bl.log_id and r.action = 'FULL_REFRESH') as is_guard_pending
    from {{ source('ctrl', 'batch_log') }} as bl
    order by bl.batch_id, bl.log_id desc
),

expected as (
    select
        l.*,
        case
            when l.ingested_ts is not null
                then (select min(t.d) from trading_day as t where t.cutoff_ts >= l.ingested_ts)
            else (select min(t.d) from trading_day as t where t.d >= l.business_date)
        end as expected_day
    from last_log as l
),

placed as (
    select e.batch_id, e.expected_day, e.is_guard_pending,
           exists (select 1 from built_day as b where b.as_of_date = e.expected_day) as is_day_built,
           count(distinct d.as_of_date) as n_days,
           count(distinct d.as_of_date) filter (where d.as_of_date <> e.expected_day) as n_wrong_days
    from expected as e
    left join dq as d on d.batch_id = e.batch_id
    group by e.batch_id, e.expected_day, e.is_guard_pending
)

select d.as_of_date, d.batch_id, 'RECON' as problem
from dq as d
inner join last_log as l on l.batch_id = d.batch_id
where l.status = 'LOADED' and d.rows_landing <> d.rows_valid + d.rows_rejected

union all
select d.as_of_date, d.batch_id, 'LANDING'
from dq as d
inner join last_log as l on l.batch_id = d.batch_id
where d.rows_landing <> l.rows_loaded

union all
select expected_day, batch_id, 'WRONG_DAY'
from placed
where n_wrong_days > 0

union all
select expected_day, batch_id, 'MISSING_BATCH'
from placed
where n_days = 0 and is_day_built and not is_guard_pending
