{{ config(tags = ['staging']) }}

-- GT-STG-UNIQUE: khử trùng trong một lần thấy (ingested_ts, cùng cách gom với macro stg_batch_dup_cols) đúng.
-- Bổ sung cho GT-STG-KEYTS (đếm count(distinct hash_diff) nên không thấy dòng trùng y hệt) và GT-STG-RECON
-- (vẫn cân khi dòng đi nhầm view). Hai vế:
--   1. DUP_KEPT_TWICE: mỗi (ingested_ts, khóa) có tối đa một dòng hợp lệ.
--   2. DUP_NOT_IDENTICAL: dòng bị loại DUPLICATE_ROW/DUPLICATE_EVENT phải cùng hash_diff với dòng được giữ;
--      khác hash_diff là xung đột bị phân loại nhầm thành trùng (dòng đầu lọt vào view hợp lệ).
-- Phép thử âm:
--   - xóa nhánh `_dup_rank > 1` ở stg_finova_app__events_rows() -> vế 1 đỏ 12 khóa (lô CAP-MG-0060).
--   - xóa nhánh `_has_conflict` ở stg_flex__broker_rows() rồi chèn dòng BRK001 khác email vào cùng lô
--     (DB thử) -> vế 2 đỏ; KEYTS và vế 1 vẫn xanh vì nhánh trùng đã che.

{% set checks = [
    ('stg_flex__regrp', ['grpid'], 'sat_regrp_hd'),
    ('stg_flex__broker', ['broker_id'], 'sat_broker_profile_hd'),
    ('stg_flex__reaflnk', ['autoid'], 'sat_reaflnk_hd'),
    ('stg_ref__nav', ['afacctno', 'tx_date'], 'sat_account_nav_hd'),
    ('stg_finova_app__events', ['event_id'], 'nhl_broker_event_hd'),
    ('stg_manual__kpi', ['broker_id'], 'sat_broker_kpi_hd'),
] %}

{% for model, keys, hd in checks %}
select '{{ model }}' as model_name, 'DUP_KEPT_TWICE' as problem,
       string_agg(batch_id, ',' order by batch_id) as batch_ids,
       concat_ws('|', {{ keys | join(', ') }}) as business_key, ingested_ts
from {{ ref(model) }}
group by {{ keys | join(', ') }}, ingested_ts
having count(*) > 1

union all

select '{{ model }}', 'DUP_NOT_IDENTICAL', r.batch_id,
       concat_ws('|', {% for k in keys %}r.{{ k }}{% if not loop.last %}, {% endif %}{% endfor %}), r.ingested_ts
from {{ ref(model ~ '__rejected') }} r
where r.reason_code in ('DUPLICATE_ROW', 'DUPLICATE_EVENT')
  and not exists (
      select 1
      from {{ ref(model) }} v
      where v.ingested_ts = r.ingested_ts
        and v.{{ hd }} = r.{{ hd }}
        {% for k in keys %}and v.{{ k }} = r.{{ k }}
        {% endfor %}
  )
{% if not loop.last %}union all{% endif %}
{% endfor %}
