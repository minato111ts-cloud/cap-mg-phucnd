-- PIT môi giới theo ngày, grain: (as_of_date, broker_hk). Mẫu T-BV (E.5).
-- Con trỏ (ingested_ts) tới phiên bản hồ sơ và chỉ tiêu hiệu lực tại cutoff(D), đọc từ view as-of với GUC của D.
-- Không chứa thuộc tính, không tính chỉ số (Q18).
with profile as (
    select broker_hk, ingested_ts
    from {{ ref('asof__sat_broker_profile__flex') }}
),

kpi as (
    select broker_hk, ingested_ts
    from {{ ref('asof__sat_broker_kpi__manual') }}
),

pit as (
    select
        {{ asof_var_date() }} as as_of_date,
        {{ asof_var_cutoff() }} as cutoff_ts,
        coalesce(p.broker_hk, k.broker_hk) as broker_hk,
        p.ingested_ts as sat_broker_profile_ingested_ts,
        k.ingested_ts as sat_broker_kpi_ingested_ts
    from profile as p
    full outer join kpi as k on k.broker_hk = p.broker_hk
)

select * from pit
