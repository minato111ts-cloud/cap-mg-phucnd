{{ config(tags = ['dv_bv']) }}

-- GT-BV-PTR (Bảng 85): con trỏ khác NULL của PIT trỏ tới phiên bản có thật trong satellite, và ingested_ts của con
-- trỏ <= cutoff_ts. cutoff_ts suy từ as_of_date, độc lập với GUC mà view as-of đọc.
-- Phép thử âm: đặt finova.asof_cutoff muộn hơn một ngày trong asof_session -> đỏ (con trỏ sau cutoff_ts).

{% set checks = [
    ('pit_broker_daily', 'broker_hk', 'sat_broker_profile_ingested_ts', 'sat_broker_profile__flex', false),
    ('pit_broker_daily', 'broker_hk', 'sat_broker_kpi_ingested_ts', 'sat_broker_kpi__manual', false),
    ('pit_account_daily', 'account_hk', 'sat_account_nav_ingested_ts', 'sat_account_nav_daily__flex', true),
] %}

{% for pit, key, ptr, sat, by_day in checks %}
select '{{ pit }}.{{ ptr }}' as pointer, p.as_of_date, p.{{ key }} as parent_hk, p.{{ ptr }} as pointer_ts,
       case when p.{{ ptr }} > p.cutoff_ts then 'AFTER_CUTOFF' else 'NOT_FOUND' end as problem
from {{ ref(pit) }} as p
where p.{{ ptr }} is not null
  and (
      p.{{ ptr }} > p.cutoff_ts
      or not exists (
          select 1
          from {{ ref(sat) }} as s
          where s.{{ key }} = p.{{ key }}
            and s.ingested_ts = p.{{ ptr }}
            {%- if by_day %}
            and s.business_date = p.as_of_date
            {%- endif %}
      )
  )
{% if not loop.last %}union all{% endif %}
{% endfor %}
