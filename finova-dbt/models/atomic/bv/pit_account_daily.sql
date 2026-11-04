-- PIT tiểu khoản theo ngày, grain: (as_of_date, account_hk). Mẫu T-BV (E.5).
-- Con trỏ tới phiên bản NAV của đúng ngày D (business_date = as_of_date) hệ thống biết tại cutoff(D).
-- Tiểu khoản không có NAV của ngày D thì không có dòng. Không chứa giá trị NAV (Q18).
with nav as (
    select account_hk, ingested_ts
    from {{ ref('asof__sat_account_nav_daily__flex') }}
    where business_date = {{ asof_var_date() }}
),

pit as (
    select
        {{ asof_var_date() }} as as_of_date,
        {{ asof_var_cutoff() }} as cutoff_ts,
        n.account_hk,
        n.ingested_ts as sat_account_nav_ingested_ts
    from nav as n
)

select * from pit
