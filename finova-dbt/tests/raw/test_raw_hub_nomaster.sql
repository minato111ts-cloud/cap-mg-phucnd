{{ config(tags = ['dv_raw'], severity = 'warn') }}

-- GT-HUB-NOMASTER (warn, Bảng 85): khóa hub chưa có satellite của nguồn làm chủ. Hub nạp từ mọi staging mang khóa
-- (DEC-ELT-HUBSRC), nên khóa chỉ thấy ở nguồn khác (cha DQ-MOCOI CN9, mã môi giới chỉ có ở sự kiện/chỉ tiêu) lộ ra ở đây.
-- hub_account không xét: đề CAP-MG không có nguồn chủ của tiểu khoản (AFMAST).
-- Dữ liệu đề: 1 khóa (CN9, khớp DQ-MOCOI ở staging).

{% set checks = [
    ('hub_broker', 'broker_hk', 'broker_id', 'sat_broker_profile__flex'),
    ('hub_regrp', 'regrp_hk', 'grpid', 'sat_regrp__flex'),
    ('hub_reaflnk', 'reaflnk_hk', 'autoid', 'sat_reaflnk__flex'),
] %}

{% for hub, hk, bk, sat in checks %}
select '{{ hub }}' as hub_name, h.{{ bk }} as business_key, h.record_source, h.ingested_ts
from {{ ref(hub) }} h
where not exists (select 1 from {{ ref(sat) }} s where s.{{ hk }} = h.{{ hk }})
{% if not loop.last %}union all{% endif %}
{% endfor %}
