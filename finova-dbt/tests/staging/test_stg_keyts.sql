{{ config(tags = ['staging']) }}

-- GT-STG-KEYTS (Bảng 85): không có hai dòng hợp lệ cùng (khóa nghiệp vụ, ingested_ts) mà khác hash_diff
-- của cùng satellite. Nếu có, raw vault không biết phiên bản nào là "thấy lần đầu".
-- Phép thử âm: bỏ nhánh CONFLICT_IN_BATCH trong một macro stg_*_rows rồi nhân đôi một dòng landing
-- với giá trị khác -> test đỏ.

{% set checks = [
    ('stg_flex__regrp', 'grpid', 'sat_regrp_hd'),
    ('stg_flex__broker', 'broker_id', 'sat_broker_profile_hd'),
    ('stg_flex__reaflnk', 'autoid', 'sat_reaflnk_hd'),
    ('stg_ref__nav', "afacctno || '|' || tx_date::text", 'sat_account_nav_hd'),
    ('stg_finova_app__events', 'event_id', 'nhl_broker_event_hd'),
    ('stg_manual__kpi', 'broker_id', 'sat_broker_kpi_hd'),
] %}

{% for model, key, hd in checks %}
select '{{ model }}' as model_name, {{ key }} as business_key, ingested_ts, count(distinct {{ hd }}) as hd_versions
from {{ ref(model) }}
group by {{ key }}, ingested_ts
having count(distinct {{ hd }}) > 1
{% if not loop.last %}union all{% endif %}
{% endfor %}
