-- P-MG-REUSE: tiểu khoản, CAP-MG-BOOKNAV, số tương tác 30 ngày tính cho người đang mang mã BRK017. As-of 12/05, 15/05.
select as_of_date as as_of,
       broker_key || ': ' || n_accounts || ' tiểu khoản; CAP-MG-BOOKNAV = ' || trim_scale(book_nav)
       || '; tương tác 30 ngày = ' || interactions_30d as value
from mart.met_broker_daily
where as_of_date in ('2026-05-12', '2026-05-15') and broker_id = 'BRK017'
order by as_of_date;
