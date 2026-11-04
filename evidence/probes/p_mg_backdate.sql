-- P-MG-BACKDATE: môi giới chăm sóc 9994000016 tại 28/04, khi dựng lại ngày 28/04 sau ngày 06/05 (full refresh dựng lại
-- mọi ngày; as-of chỉ dùng phiên bản có ingested_ts <= cutoff(28/04)).
select as_of_date as as_of, broker_id || ' (' || care_basis || ')' as value
from mart.dim_account_care_daily
where as_of_date = '2026-04-28' and account_id = '9994000016';
