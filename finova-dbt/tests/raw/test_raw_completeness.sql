{{ config(tags = ['dv_raw']) }}

-- Đủ dòng ở raw vault (DEC-ELT-REJECT: vault giữ mọi dòng staging dựng được khóa), xét staging có ingested_ts <= hi_ts:
--   MISSING_KEY: khóa hub, link, nhl của staging không có trong bảng vault;
--   STALE_VERSION: phiên bản mới nhất của satellite khác hashdiff của dòng staging cuối cùng của khóa (bỏ sót phiên bản).
-- PT-FULL chỉ so hai cách nạp với nhau; test này so vault với staging, nên bắt được lỗi giống nhau ở cả hai cách.
-- Phép thử âm: dv_load_sat chỉ ghi phiên bản đầu mỗi khóa ("and seq.rn = 1") -> STALE_VERSION đỏ ở 4 satellite.
-- Test không bắt lỗi ghi sai ingested_ts mà phiên bản cuối vẫn đúng (vd lag sắp ngược); lỗi đó thuộc PT-ABA, PT-FULL.

{% set hi = "'" ~ var('hi_ts') ~ "'::timestamptz" %}

{% set keys = [
    ('stg_flex__broker', 'broker_hk', 'hub_broker', 'broker_hk'),
    ('stg_flex__reaflnk', 'broker_hk', 'hub_broker', 'broker_hk'),
    ('stg_finova_app__events', 'broker_hk', 'hub_broker', 'broker_hk'),
    ('stg_manual__kpi', 'broker_hk', 'hub_broker', 'broker_hk'),
    ('stg_flex__reaflnk', 'account_hk', 'hub_account', 'account_hk'),
    ('stg_ref__nav', 'account_hk', 'hub_account', 'account_hk'),
    ('stg_finova_app__events', 'account_hk', 'hub_account', 'account_hk'),
    ('stg_flex__regrp', 'regrp_hk', 'hub_regrp', 'regrp_hk'),
    ('stg_flex__regrp', 'parent_regrp_hk', 'hub_regrp', 'regrp_hk'),
    ('stg_flex__broker', 'regrp_hk', 'hub_regrp', 'regrp_hk'),
    ('stg_flex__reaflnk', 'reaflnk_hk', 'hub_reaflnk', 'reaflnk_hk'),
    ('stg_flex__broker', 'link_broker_regrp_hk', 'link_broker_regrp', 'link_broker_regrp_hk'),
    ('stg_flex__regrp', 'link_regrp_parent_hk', 'link_regrp_parent', 'link_regrp_parent_hk'),
    ('stg_flex__reaflnk', 'link_reaflnk_hk', 'link_reaflnk', 'link_reaflnk_hk'),
    ('stg_finova_app__events', 'nhl_broker_event_hk', 'nhl_broker_event', 'nhl_broker_event_hk'),
] %}

{% set sats = [
    ('stg_flex__broker', 'broker_hk', 'sat_broker_profile_hd', 'sat_broker_profile__flex', none),
    ('stg_flex__regrp', 'regrp_hk', 'sat_regrp_hd', 'sat_regrp__flex', none),
    ('stg_flex__reaflnk', 'reaflnk_hk', 'sat_reaflnk_hd', 'sat_reaflnk__flex', none),
    ('stg_manual__kpi', 'broker_hk', 'sat_broker_kpi_hd', 'sat_broker_kpi__manual', none),
    ('stg_ref__nav', 'account_hk', 'sat_account_nav_hd', 'sat_account_nav_daily__flex', 'tx_date'),
] %}

{% for stg, col, tgt, tgt_col in keys %}
select 'MISSING_KEY' as problem, '{{ stg }}.{{ col }} -> {{ tgt }}' as check_name, count(*) as n_keys
from (select distinct {{ col }} as k from {{ ref(stg) }} where ingested_ts <= {{ hi }} and {{ col }} is not null) s
where not exists (select 1 from {{ ref(tgt) }} t where t.{{ tgt_col }} = s.k)
having count(*) > 0
union all
{% endfor %}

{% for stg, parent, hd, sat, bd in sats %}
select 'STALE_VERSION', '{{ stg }} -> {{ sat }}', count(*)
from (
    select distinct on ({{ parent }}{% if bd %}, {{ bd }}{% endif %})
           {{ parent }} as k, {% if bd %}{{ bd }}{% else %}null::date{% endif %} as bd, {{ hd }} as hd
    from {{ ref(stg) }}
    where ingested_ts <= {{ hi }}
    order by {{ parent }}{% if bd %}, {{ bd }}{% endif %}, ingested_ts desc
) s
left join lateral (
    select t.hash_diff
    from {{ ref(sat) }} t
    where t.{{ parent }} = s.k
      {%- if bd %} and t.business_date = s.bd{% endif %}
      and t.ingested_ts <= {{ hi }}
    order by t.ingested_ts desc
    limit 1
) v on true
where v.hash_diff is distinct from s.hd
having count(*) > 0
{% if not loop.last %}union all{% endif %}
{% endfor %}
