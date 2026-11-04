-- P-MG-RESTRUCT: đơn vị cha của nhóm G4; số tiểu khoản theo chi nhánh. As-of 29/04, 04/05.
-- Cha của G4 đọc từ đường dẫn cây của D trên dim_broker_org_daily (phần tử ngay trước G4); số tiểu khoản theo chi
-- nhánh cộng met_broker_daily theo branch_id của D.
with g4 as (
    select distinct as_of_date, org_path
    from mart.dim_broker_org_daily
    where as_of_date in ('2026-04-29', '2026-05-04') and grp_id = 'G4'
),
branch as (
    select d.as_of_date, d.branch_id, sum(m.n_accounts) as n
    from mart.met_broker_daily as m
    join mart.dim_broker_org_daily as d on d.as_of_date = m.as_of_date and d.broker_key = m.broker_key
    where m.as_of_date in ('2026-04-29', '2026-05-04')
    group by d.as_of_date, d.branch_id
)
select g.as_of_date as as_of,
       'Cha G4 = ' || (string_to_array(g.org_path, ' > '))[array_length(string_to_array(g.org_path, ' > '), 1) - 1]
       || ' | ' || (select string_agg(coalesce(b.branch_id, 'NULL') || ': ' || b.n, '; ' order by b.branch_id)
                    from branch as b where b.as_of_date = g.as_of_date) as value
from g4 as g
order by g.as_of_date;
