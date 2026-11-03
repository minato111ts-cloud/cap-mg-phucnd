{{ config(tags = ['dv_raw']) }}

-- GT-ESAT-ONEACTIVE (Bảng 85): tại mọi thời điểm ghi, mỗi driving key có tối đa một link hiệu lực.
-- Trạng thái của một link tại thời điểm T là dòng esat mới nhất có ingested_ts <= T.
-- Phép thử âm: bỏ nhánh "đóng link cũ" (union all thứ hai) trong dv_load_esat_dk -> đỏ ở G4 từ CAP-MG-0051.

{% set checks = [
    ('esat_regrp_parent__flex', 'link_regrp_parent', 'link_regrp_parent_hk', 'regrp_hk'),
    ('esat_broker_regrp__flex', 'link_broker_regrp', 'link_broker_regrp_hk', 'broker_hk'),
] %}

{% for esat, link, lhk, dk in checks %}
select * from (
    with e as (
        select e.{{ lhk }} as link_hk, l.{{ dk }} as driving_key, e.ingested_ts, e.is_active
        from {{ ref(esat) }} e
        join {{ ref(link) }} l on l.{{ lhk }} = e.{{ lhk }}
    ),
    points as (
        select distinct driving_key, ingested_ts from e
    ),
    state_at as (
        select p.driving_key, p.ingested_ts, x.link_hk, x.is_active
        from points p
        cross join lateral (
            select distinct on (e2.link_hk) e2.link_hk, e2.is_active
            from e e2
            where e2.driving_key = p.driving_key and e2.ingested_ts <= p.ingested_ts
            order by e2.link_hk, e2.ingested_ts desc
        ) x
    )
    select '{{ esat }}' as esat_name, driving_key, ingested_ts, count(*) as active_links
    from state_at
    where is_active
    group by driving_key, ingested_ts
    having count(*) > 1
) t_{{ loop.index }}
{% if not loop.last %}union all{% endif %}
{% endfor %}
