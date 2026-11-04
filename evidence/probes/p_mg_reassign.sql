-- P-MG-REASSIGN: môi giới chăm sóc các tiểu khoản 9994000001…9994000015; CAP-MG-BOOKNAV của BRK003. As-of 08/05, 11/05.
with care as (
    select as_of_date, broker_id, count(*) as n
    from mart.dim_account_care_daily
    where as_of_date in ('2026-05-08', '2026-05-11')
      and account_id between '9994000001' and '9994000015'
    group by as_of_date, broker_id
),
nav as (
    select as_of_date, book_nav
    from mart.met_broker_daily
    where as_of_date in ('2026-05-08', '2026-05-11') and broker_id = 'BRK003'
)
select c.as_of_date as as_of,
       string_agg(coalesce(c.broker_id, 'NULL') || ' x' || c.n, '; ' order by c.broker_id)
           || ' | CAP-MG-BOOKNAV BRK003 = ' || coalesce(trim_scale(max(n.book_nav))::text, 'NULL') as value
from care as c
left join nav as n on n.as_of_date = c.as_of_date
group by c.as_of_date
order by c.as_of_date;
