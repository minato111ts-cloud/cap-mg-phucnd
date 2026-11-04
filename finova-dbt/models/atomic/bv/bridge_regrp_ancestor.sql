-- Bridge đơn vị - cấp trên theo ngày, grain: (as_of_date, regrp_hk, ancestor_regrp_hk). Mẫu T-BV (E.5).
-- Cây của D dựng từ parentid của asof.sat_regrp__flex (đơn vị đã xóa đã bị view bỏ); depth 0 là chính đơn vị.
-- Mồ côi (DQ-MOCOI, DEC-CAP-MG-ORPHAN): chuỗi cấp trên dừng ở một đơn vị cha không có trong cây của D. Đơn vị đứng
-- đầu chuỗi đó cùng các đơn vị dưới nó là một nhánh mồ côi:
--   - nhánh có môi giới tại D: giữ, treo vào nút ảo UNKNOWN dưới gốc, is_orphan_branch = true; không mất số liệu;
--   - nhánh không có môi giới: không vào cây ngày đó (đơn vị không có thật, không ảnh hưởng số liệu).
-- Nguồn sửa cha thì cây của ngày nạp bản sửa tự nối về cha thật. Ngày cũ giữ nguyên theo as-of.
-- Vòng (DQ-VONG) không bị bỏ: đi tới đơn vị đã gặp thì ghi dòng đó rồi dừng, để TC-CAP-MG-TREE phát hiện.
with recursive unit as (
    select regrp_hk, grpid, parentid
    from {{ ref('asof__sat_regrp__flex') }}
),

walk (regrp_hk, ancestor_regrp_hk, ancestor_parentid, depth, path, is_cycle) as (
    select u.regrp_hk, u.regrp_hk, u.parentid, 0, array[u.grpid], false
    from unit as u
    union all
    select w.regrp_hk, p.regrp_hk, p.parentid, w.depth + 1, w.path || p.grpid, p.grpid = any(w.path)
    from walk as w
    inner join unit as p on p.grpid = w.ancestor_parentid
    where not w.is_cycle
),

-- dòng cuối của chuỗi đi lên từ mỗi đơn vị
chain_end as (
    select distinct on (regrp_hk) regrp_hk, ancestor_regrp_hk, ancestor_parentid, depth, is_cycle
    from walk
    order by regrp_hk, depth desc
),

root as (
    select regrp_hk
    from unit
    where parentid is null
),

-- chuỗi dừng mà không phải ở gốc (parentid null) và không phải vì vòng: cha không có trong cây của D.
-- top_regrp_hk: đơn vị đứng đầu nhánh mồ côi (đơn vị có cha không tồn tại)
orphan as (
    select regrp_hk, ancestor_regrp_hk as top_regrp_hk, depth as top_depth
    from chain_end
    where not is_cycle and ancestor_parentid is not null
),

-- nhánh mồ côi có môi giới thuộc một đơn vị bất kỳ trong nhánh tại D
orphan_top_with_data as (
    select distinct o.top_regrp_hk
    from orphan as o
    inner join unit as u on u.regrp_hk = o.regrp_hk
    inner join {{ ref('asof__sat_broker_profile__flex') }} as b on b.grpid = u.grpid
),

kept_orphan as (
    select o.regrp_hk, o.top_depth
    from orphan as o
    inner join orphan_top_with_data as t on t.top_regrp_hk = o.top_regrp_hk
),

edges as (
    -- đơn vị không mồ côi (kể cả nằm trên vòng): chuỗi cấp trên thật
    select w.regrp_hk, w.ancestor_regrp_hk, w.depth, false as is_orphan_branch
    from walk as w
    where not exists (select 1 from orphan as o where o.regrp_hk = w.regrp_hk)

    union all
    -- nhánh mồ côi có số liệu: chuỗi thật tới đơn vị đứng đầu nhánh, rồi UNKNOWN, rồi gốc
    select w.regrp_hk, w.ancestor_regrp_hk, w.depth, true
    from walk as w
    inner join kept_orphan as k on k.regrp_hk = w.regrp_hk

    union all
    select k.regrp_hk, {{ bv_regrp_unknown_hk() }}, k.top_depth + 1, true
    from kept_orphan as k

    union all
    select k.regrp_hk, r.regrp_hk, k.top_depth + 2, true
    from kept_orphan as k
    cross join root as r

    union all
    -- nút UNKNOWN: chỉ có khi ngày D có nhánh mồ côi được giữ, và chỉ khi cây có gốc
    -- (không có gốc thì UNKNOWN không thành gốc thay, TC-CAP-MG-TREE đỏ)
    select distinct {{ bv_regrp_unknown_hk() }}, {{ bv_regrp_unknown_hk() }}, 0, true
    from kept_orphan
    where exists (select 1 from root)

    union all
    select distinct {{ bv_regrp_unknown_hk() }}, r.regrp_hk, 1, true
    from kept_orphan
    cross join root as r
),

bridge as (
    select
        {{ asof_var_date() }} as as_of_date,
        {{ asof_var_cutoff() }} as cutoff_ts,
        regrp_hk,
        ancestor_regrp_hk,
        depth,
        is_orphan_branch
    from edges
)

select * from bridge
