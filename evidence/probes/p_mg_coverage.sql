-- P-MG-COVERAGE: CAP-MG-COVER30 của BRK009 (tử/mẫu) as-of 15/05.
select as_of_date as as_of, cover30_num || '/' || cover30_den as value
from mart.met_broker_daily
where as_of_date = '2026-05-15' and broker_id = 'BRK009';
