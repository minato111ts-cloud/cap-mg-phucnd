{{ config(tags = ['dv_raw']) }}

-- GT-STS-ENUM (Bảng 85), phần chuyển trạng thái: hai dòng liền nhau của cùng khóa khác trạng thái;
-- dòng đầu không phải ACTIVE (vắng dòng sts nghĩa là ACTIVE). Tập giá trị kiểm bằng accepted_values ở _raw__models.yml.
-- Phép thử âm: bỏ so cur/prev_status trong dv_load_sts_snapshot (ghi mọi lô) -> đỏ.

{% set checks = [
    ('sts_regrp__flex', 'regrp_hk'),
    ('sts_broker__flex', 'broker_hk'),
    ('sts_reaflnk__flex', 'reaflnk_hk'),
    ('sts_broker_kpi__manual', 'broker_hk'),
] %}

{% for sts, hk in checks %}
select * from (
    select '{{ sts }}' as sts_name, {{ hk }} as parent_hk, ingested_ts, status, prev_status
    from (
        select {{ hk }}, ingested_ts, status,
               lag(status) over (partition by {{ hk }} order by ingested_ts) as prev_status,
               row_number() over (partition by {{ hk }} order by ingested_ts) as rn
        from {{ ref(sts) }}
    ) s
    where status = prev_status or (rn = 1 and status = 'ACTIVE')
) t_{{ loop.index }}
{% if not loop.last %}union all{% endif %}
{% endfor %}
