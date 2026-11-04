-- Bridge tiểu khoản - môi giới chăm sóc theo ngày, grain: (as_of_date, account_hk). Mẫu T-BV (E.5).
-- Nguồn: phân công hiệu lực tại D (asof.esat_reaflnk__flex). Tiểu khoản có nhiều phân công cùng hiệu lực (DQ-CHONGLAN)
-- chọn một theo DEC-CAP-MG-OVERLAP: FRDATE muộn hơn thắng, rồi ingested_ts, rồi AUTOID lớn hơn (C-SA-ONEBROKER).
-- is_overlap: tại D có từ hai môi giới khác nhau cùng hiệu lực trên tiểu khoản.
with assignment as (
    select account_hk, broker_hk, reaflnk_hk, link_reaflnk_hk, autoid, fr_date, ingested_ts
    from {{ ref('asof__esat_reaflnk__flex') }}
),

broker_count as (
    select account_hk, count(distinct broker_hk) as n_brokers
    from assignment
    group by account_hk
),

ranked as (
    select
        a.*,
        row_number() over (
            partition by a.account_hk
            order by a.fr_date desc,
                     a.ingested_ts desc,
                     case when a.autoid ~ '^[0-9]+$' then a.autoid::numeric end desc nulls last,
                     a.autoid desc
        ) as rn
    from assignment as a
),

bridge as (
    select
        {{ asof_var_date() }} as as_of_date,
        {{ asof_var_cutoff() }} as cutoff_ts,
        r.account_hk,
        r.broker_hk,
        r.reaflnk_hk,
        r.link_reaflnk_hk,
        c.n_brokers > 1 as is_overlap
    from ranked as r
    inner join broker_count as c on c.account_hk = r.account_hk
    where r.rn = 1
)

select * from bridge
