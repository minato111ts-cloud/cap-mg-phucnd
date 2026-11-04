-- P-MG-OVERLAP: môi giới của tiểu khoản 9994000026 ngày 05/05 (DEC-CAP-MG-OVERLAP).
select as_of_date as as_of, broker_id || ' (' || care_basis || ')' as value
from mart.dim_account_care_daily
where as_of_date = '2026-05-05' and account_id = '9994000026';
