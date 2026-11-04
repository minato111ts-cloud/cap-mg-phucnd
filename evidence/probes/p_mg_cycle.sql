-- P-MG-CYCLE: đơn vị cha của G5, G6 as-of 06/05 (lô có vòng bị loại ở staging, giữ phiên bản cây trước).
select as_of_date as as_of,
       string_agg(distinct grp_id || ' -> ' || (string_to_array(org_path, ' > '))[array_length(string_to_array(org_path, ' > '), 1) - 1],
                  '; ') as value
from mart.dim_broker_org_daily
where as_of_date = '2026-05-06' and grp_id in ('G5', 'G6')
group by as_of_date;
