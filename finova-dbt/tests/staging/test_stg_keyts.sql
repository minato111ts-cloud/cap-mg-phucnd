{{ config(tags = ['staging']) }}

-- GT-STG-KEYTS (Bảng 85): không có hai dòng hợp lệ cùng (khóa nghiệp vụ, ingested_ts) mà khác hash_diff
-- của cùng satellite. Nếu có, raw vault không biết phiên bản nào là "thấy lần đầu".
-- Phép thử âm (DB thử, chèn thẳng landing nên GT-STG-RECON cũng đỏ theo):
--   - chèn lô CAP-MG-9999 cùng ingested_ts với CAP-MG-0002, dòng BRK001 khác email, rồi gom xung đột
--     trong stg_batch_dup_cols theo batch_id thay vì ingested_ts -> test đỏ 1 khóa.
--   - chỉ bỏ nhánh CONFLICT_IN_BATCH thì test này vẫn xanh (nhánh DUPLICATE_ROW giữ dòng đầu);
--     trường hợp đó do vế DUP_NOT_IDENTICAL của test_stg_dedup bắt.

{% set checks = [
    ('stg_flex__regrp', 'grpid', 'sat_regrp_hd'),
    ('stg_flex__broker', 'broker_id', 'sat_broker_profile_hd'),
    ('stg_flex__reaflnk', 'autoid', 'sat_reaflnk_hd'),
    ('stg_flex__nav', "afacctno || '|' || tx_date::text", 'sat_account_nav_hd'),
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
