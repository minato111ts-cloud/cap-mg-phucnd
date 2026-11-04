{{ config(tags = ['dv_bv']) }}

-- TC-CAP-MG-TREE (Bảng 70): cây của ngày D không có vòng; mọi đơn vị có đường đi lên tới gốc (HO).
-- Gốc là đơn vị không có cấp trên nào ngoài chính nó; mỗi ngày đúng một gốc.
-- Phép thử âm (theo đề): nạp cây có vòng, không lọc (bỏ CYCLE_DETECTED ở staging) -> đỏ ở ngày có vòng.

with b as (
    select as_of_date, regrp_hk, ancestor_regrp_hk, depth
    from {{ ref('bridge_regrp_ancestor') }}
),

root as (
    select as_of_date, regrp_hk
    from b
    group by as_of_date, regrp_hk
    having max(depth) = 0
),

root_count as (
    select d.as_of_date, count(r.regrp_hk) as n_roots
    from (select distinct as_of_date from b) as d
    left join root as r on r.as_of_date = d.as_of_date
    group by d.as_of_date
),

self_ancestor as (
    select as_of_date, regrp_hk, 'SELF_ANCESTOR' as problem
    from b
    where ancestor_regrp_hk = regrp_hk and depth > 0
),

no_path_to_root as (
    select distinct b.as_of_date, b.regrp_hk, 'NO_PATH_TO_ROOT' as problem
    from b
    where not exists (
        select 1
        from b as b2
        inner join root as r on r.as_of_date = b2.as_of_date and r.regrp_hk = b2.ancestor_regrp_hk
        where b2.as_of_date = b.as_of_date and b2.regrp_hk = b.regrp_hk
    )
),

bad_root_count as (
    select as_of_date, null::bytea as regrp_hk, 'ROOT_COUNT_' || n_roots as problem
    from root_count
    where n_roots <> 1
),

failures as (
    select * from self_ancestor
    union all
    select * from no_path_to_root
    union all
    select * from bad_root_count
)

select * from failures
