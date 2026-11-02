{{ config(tags = ['staging']) }}

-- DQ-VONG: trong mỗi lô, các dòng hợp lệ của stg_flex__regrp không được tạo vòng (mọi độ dài).
-- Dò lại độc lập với macro (đi ngược lên cha trên chính view hợp lệ), nên bắt được khi logic
-- CYCLE_DETECTED trong macro bị hỏng. TC-CAP-MG-TREE ở Business Vault kiểm thêm đường lên HO.
-- Phép thử âm: xóa nhánh `when _in_cycle then 'CYCLE_DETECTED'` -> test đỏ ở lô CAP-MG-0061 (G5, G6).

with recursive edges as (
    select distinct batch_id, grpid, parentid
    from {{ ref('stg_flex__regrp') }}
    where parentid is not null
),

walk (batch_id, start_id, cur_id, depth) as (
    select batch_id, grpid, parentid, 1 from edges
    union all
    select w.batch_id, w.start_id, e.parentid, w.depth + 1
    from walk w
    join edges e on e.batch_id = w.batch_id and e.grpid = w.cur_id
    where w.cur_id <> w.start_id and w.depth < 100
)

select distinct batch_id, start_id as grpid
from walk
where cur_id = start_id
