{{ config(tags = ['gold']) }}

-- TC-CAP-MG-ROLLUP (Bảng 70): tổng cấp chi nhánh bằng tổng các nhóm thuộc chi nhánh theo cây của ngày D.
--   Vế Gold: cộng met_broker_daily theo branch_id của dim_broker_org_daily.
--   Vế cây của D: cộng met_broker_daily theo đơn vị của môi giới (grp_id), rồi dồn đơn vị lên chi nhánh theo
--   bridge_regrp_ancestor của chính D (chi nhánh = đơn vị con trực tiếp của gốc; đơn vị thuộc chi nhánh khi chi nhánh
--   là cấp trên ở mọi độ sâu, kể cả chính nó).
-- So cả tử, mẫu của CAP-MG-COVER30: tỷ lệ cấp trên là cộng tử, cộng mẫu rồi chia (Bảng 24, kiểu ratio).
-- Phép thử âm (theo đề): dùng cây của ngày cuối cho mọi ngày ở dim_broker_org_daily -> đỏ ở ngày cây khác ngày cuối.

with met as (
    select m.as_of_date, m.n_accounts, m.book_nav, m.cover30_num, m.cover30_den, d.branch_id, d.grp_id
    from {{ ref('met_broker_daily') }} as m
    inner join {{ ref('dim_broker_org_daily') }} as d
        on d.as_of_date = m.as_of_date and d.broker_key = m.broker_key
),

gold_branch as (
    select as_of_date, branch_id, sum(n_accounts) as n_accounts, sum(book_nav) as book_nav,
           sum(cover30_num) as cover30_num, sum(cover30_den) as cover30_den
    from met
    where branch_id is not null
    group by as_of_date, branch_id
),

unit_total as (
    select as_of_date, grp_id, sum(n_accounts) as n_accounts, sum(book_nav) as book_nav,
           sum(cover30_num) as cover30_num, sum(cover30_den) as cover30_den
    from met
    group by as_of_date, grp_id
),

-- mã đơn vị theo khóa băm (không đổi theo thời gian); nút ảo UNKNOWN không có trong satellite
unit_code as (
    select distinct regrp_hk, grpid
    from {{ ref('sat_regrp__flex') }}
    union all
    select {{ bv_regrp_unknown_hk() }}, {{ bv_regrp_unknown_bk() }}
),

tree as (
    select a.as_of_date, a.regrp_hk, a.ancestor_regrp_hk, a.depth
    from {{ ref('bridge_regrp_ancestor') }} as a
    where a.as_of_date in (select distinct as_of_date from met)
),

root as (
    select as_of_date, regrp_hk
    from tree
    group by as_of_date, regrp_hk
    having max(depth) = 0
),

branch as (
    select t.as_of_date, t.regrp_hk as branch_hk
    from tree as t
    inner join root as r on r.as_of_date = t.as_of_date and r.regrp_hk = t.ancestor_regrp_hk
    where t.depth = 1
),

tree_branch as (
    select br.as_of_date, bc.grpid as branch_id,
           sum(u.n_accounts) as n_accounts, sum(u.book_nav) as book_nav,
           sum(u.cover30_num) as cover30_num, sum(u.cover30_den) as cover30_den
    from branch as br
    inner join unit_code as bc on bc.regrp_hk = br.branch_hk
    inner join tree as t on t.as_of_date = br.as_of_date and t.ancestor_regrp_hk = br.branch_hk
    inner join unit_code as uc on uc.regrp_hk = t.regrp_hk
    inner join unit_total as u on u.as_of_date = br.as_of_date and u.grp_id = uc.grpid
    group by br.as_of_date, bc.grpid
),

compared as (
    select
        coalesce(g.as_of_date, t.as_of_date) as as_of_date,
        coalesce(g.branch_id, t.branch_id) as branch_id,
        g.n_accounts as gold_n_accounts, t.n_accounts as tree_n_accounts,
        g.book_nav as gold_book_nav, t.book_nav as tree_book_nav,
        g.cover30_num as gold_cover30_num, t.cover30_num as tree_cover30_num,
        g.cover30_den as gold_cover30_den, t.cover30_den as tree_cover30_den
    from gold_branch as g
    full outer join tree_branch as t on t.as_of_date = g.as_of_date and t.branch_id = g.branch_id
)

select *
from compared
where gold_n_accounts is distinct from tree_n_accounts
   or gold_book_nav is distinct from tree_book_nav
   or gold_cover30_num is distinct from tree_cover30_num
   or gold_cover30_den is distinct from tree_cover30_den
