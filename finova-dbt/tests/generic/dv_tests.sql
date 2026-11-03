{#
  Generic test chung của raw vault (Bảng 85). Project không dùng dbt_utils nên tự viết.
#}

{# GT-HUB-UNIQ (bkcc, bk), GT-LNK-UNIQ (khóa hub), GT-SAT-PK (khóa cha[, business_date], ingested_ts) #}
{% test dv_unique_combination(model, columns) %}
select {{ columns | join(', ') }}, count(*) as n_rows
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1
{% endtest %}


{# GT-HUB-SHAPE, GT-LNK-SHAPE: bảng có đúng các cột cho phép (Q3: hub chỉ có khóa băm, bkcc, khóa nghiệp vụ, cột hệ thống;
   link không có cột thuộc tính). Mỗi dòng trả về là một cột thừa hoặc thiếu. #}
{% test dv_shape(model, allowed) %}
with actual as (
    select column_name::text as column_name
    from information_schema.columns
    where table_schema = '{{ model.schema }}' and table_name = '{{ model.identifier }}'
),
expected as (
    select unnest(array[{% for c in allowed %}'{{ c }}'{% if not loop.last %}, {% endif %}{% endfor %}]::text[]) as column_name
)
select 'UNEXPECTED' as problem, a.column_name from actual a where a.column_name not in (select column_name from expected)
union all
select 'MISSING', e.column_name from expected e where e.column_name not in (select column_name from actual)
{% endtest %}


{# GT-SAT-NOREDUNDANT (warn): hai phiên bản liền nhau của cùng khóa (cùng ngày với satellite theo ngày) không cùng hash_diff #}
{% test dv_sat_no_redundant(model, parent, partition_extra=[]) %}
{%- set part = [parent] + partition_extra -%}
with s as (
    select {{ part | join(', ') }}, ingested_ts, hash_diff,
           lag(hash_diff) over (partition by {{ part | join(', ') }} order by ingested_ts) as prev_hd
    from {{ model }}
)
select * from s where hash_diff = prev_hd
{% endtest %}
