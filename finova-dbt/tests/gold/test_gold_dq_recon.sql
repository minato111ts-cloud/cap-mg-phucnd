{{ config(tags = ['gold']) }}

-- D-DQ khớp với ctrl.batch_log và __rejected (Bảng 25):
--   RECON: lô LOADED có rows_landing = rows_valid + rows_rejected (GT-STG-RECON ở Gold);
--   LANDING: rows_landing = batch_log.rows_loaded của dòng sổ cuối của lô;
--   MISSING_BATCH: mọi lô trong sổ có mặt ở đúng một ngày D của dq_mg_daily, xét các lô có ingested_ts không quá
--   cutoff của ngày D lớn nhất đã dựng; lô không nạp (không có ingested_ts) xét theo business_date. Lô T-GUARD đã chặn
--   mà chưa được full refresh xử lý nằm ngoài mọi cửa sổ theo ngày cho tới lần full refresh (RV-10), nên chỉ đòi
--   không quá một ngày.
-- Phép thử âm: bỏ một view __rejected khỏi danh sách nguồn của dq_mg_daily -> RECON đỏ.

with dq as (
    select distinct as_of_date, batch_id, source_table, rows_landing, rows_valid, rows_rejected
    from {{ ref('dq_mg_daily') }}
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

built as (
    select max(cutoff_ts) as max_cutoff, max(as_of_date) as max_date from {{ ref('dq_mg_daily') }}
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
select null::date, l.batch_id, 'MISSING_BATCH_' || count(distinct d.as_of_date)
from last_log as l
cross join built as b
left join dq as d on d.batch_id = l.batch_id
where coalesce(l.ingested_ts <= b.max_cutoff, l.business_date <= b.max_date)
group by l.batch_id, l.is_guard_pending
having count(distinct d.as_of_date) <> 1
   and not (l.is_guard_pending and count(distinct d.as_of_date) = 0)
