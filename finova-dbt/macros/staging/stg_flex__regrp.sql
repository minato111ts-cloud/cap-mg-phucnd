{#
  Staging flex_regrp (cây đơn vị). Vòng (DQ-VONG) dò bằng CTE đệ quy trên từng lô: bắt vòng mọi độ dài
  (A->A, A->B->A, A->B->C->A...), không chỉ vòng 2 nút. Đây là tra khóa trong cùng nguồn, cùng lô.
  Dòng nằm trên vòng -> CYCLE_DETECTED; Business Vault giữ phiên bản cây trước (DEC-CAP-MG-CYCLE).
  Cha không có trong lô (DQ-MOCOI) vẫn nhận; test warn test_stg_regrp_parent_missing đếm.
#}

{% macro stg_flex__regrp_columns() -%}
    bkcc_regrp, bk_regrp, regrp_hk, parent_regrp_hk,
    sat_regrp_hd,
    grpid, parentid, grpname, grplevel, effdate, status,
    record_source, source_id, batch_id, ingested_ts, event_ts, record_hash, source_row_no
{%- endmacro %}


{% macro stg_flex__regrp_rows() -%}
with recursive parsed as (
    select
        l.source_id, l.batch_id, l.ingested_ts, l.event_ts, l.record_hash, l.source_row_no,
        {{ stg_code('l.grpid') }} as grpid,
        {{ stg_code('l.parentid') }} as parentid,
        nullif(btrim(l.grpname), '') as grpname,
        {{ stg_parse_int('l.grplevel') }} as grplevel,
        {{ stg_parse_date('l.effdate') }} as effdate,
        {{ stg_code('l.status') }} as status
    from {{ source('landing', 'flex_regrp') }} l
),

edges as (
    select distinct batch_id, grpid, parentid
    from parsed
    where grpid is not null and parentid is not null
),

-- Đi ngược lên cha từ mỗi nút; quay lại chính nút xuất phát nghĩa là nút nằm trên vòng
walk (batch_id, start_id, cur_id, depth) as (
    select batch_id, grpid, parentid, 1 from edges
    union all
    select w.batch_id, w.start_id, e.parentid, w.depth + 1
    from walk w
    join edges e on e.batch_id = w.batch_id and e.grpid = w.cur_id
    where w.cur_id <> w.start_id and w.depth < 100
),

cycle_nodes as (
    select distinct batch_id, start_id as grpid from walk where cur_id = start_id
),

hashed as (
    select
        p.*,
        c.grpid is not null as _in_cycle,
        {{ dv_hash(["'FLEX'", 'p.grpid']) }} as regrp_hk,
        case when p.parentid is not null then {{ dv_hash(["'FLEX'", 'p.parentid']) }} end as parent_regrp_hk,
        {{ dv_hash([
            'p.parentid', 'p.grpname',
            {'expr': 'p.grplevel', 'type': 'text'},
            'p.effdate::date', 'p.status'
        ]) }} as sat_regrp_hd
    from parsed p
    left join cycle_nodes c on c.batch_id = p.batch_id and c.grpid = p.grpid
),

checked as (
    select h.*, {{ stg_batch_dup_cols('grpid', 'sat_regrp_hd') }}
    from hashed h
)

select
    'FLEX' as bkcc_regrp,
    grpid as bk_regrp,
    regrp_hk, parent_regrp_hk, sat_regrp_hd,
    grpid, parentid, grpname, grplevel, effdate, status,
    'flex.flex_regrp' as record_source,
    source_id, batch_id, ingested_ts, event_ts, record_hash, source_row_no,
    case
        when grpid is null then 'KEY_NULL'
        when grpid !~ '^(HO|CN[0-9]+|G[0-9]+)$' then 'KEY_FORMAT'
        when status is null or status not in ('A', 'C') then 'ALLCODE_UNKNOWN'
        when _in_cycle then 'CYCLE_DETECTED'
        when _has_conflict then 'CONFLICT_IN_BATCH'
        when _dup_rank > 1 then 'DUPLICATE_ROW'
    end as reason_code
from checked
{%- endmacro %}
