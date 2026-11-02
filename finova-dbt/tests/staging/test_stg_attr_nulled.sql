{{ config(tags = ['staging'], severity = 'warn') }}

-- null_and_count (hợp đồng, mục 2.5): cột thuộc tính sai mẫu/không ép kiểu được thì staging nhận dòng và để NULL.
-- Test warn này là phần "count": mỗi dòng ra là một ô có giá trị ở landing nhưng NULL ở view hợp lệ,
-- để D-DQ báo cáo thay vì mất âm thầm. Gồm cả giờ thiết bị gửi sai (event_ts đã lùi về server_ts).
-- Phép thử âm: DB thử, đổi một GRPID ở landing.flex_broker thành 'X1' -> warn 1 dòng (grpid) và
--   test not_null warn của grpid cũng tăng 1.

{% set checks = [
    ('stg_flex__broker', 'flex_broker', 'grpid', 'grpid'),
    ('stg_flex__broker', 'flex_broker', 'joindate', 'join_date'),
    ('stg_flex__broker', 'flex_broker', 'leavedate', 'leave_date'),
    ('stg_flex__regrp', 'flex_regrp', 'parentid', 'parentid'),
    ('stg_flex__regrp', 'flex_regrp', 'grplevel', 'grplevel'),
    ('stg_flex__regrp', 'flex_regrp', 'effdate', 'effdate'),
    ('stg_flex__reaflnk', 'flex_reaflnk', 'lastchange', 'lastchange'),
    ('stg_finova_app__events', 'finova_app_events', 'raw_event_ts', 'device_event_ts'),
    ('stg_finova_app__events', 'finova_app_events', 'duration_sec', 'duration_sec'),
    ('stg_finova_app__events', 'finova_app_events', 'outcome', 'outcome'),
] %}

{% for model, landing_table, raw_col, stg_col in checks %}
select '{{ model }}' as model_name, '{{ stg_col }}' as column_name, s.batch_id, s.source_row_no,
       l.{{ raw_col }} as raw_value
from {{ ref(model) }} s
join {{ source('landing', landing_table) }} l
  on l.batch_id = s.batch_id and l.source_row_no = s.source_row_no
where nullif(btrim(l.{{ raw_col }}), '') is not null
  and s.{{ stg_col }} is null
{% if not loop.last %}union all{% endif %}
{% endfor %}
