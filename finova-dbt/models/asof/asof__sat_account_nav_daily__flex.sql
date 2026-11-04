{{ config(alias='sat_account_nav_daily__flex') }}
-- NAV as-of D, grain: (account_hk, business_date ≤ D). CAP-MG-BOOKNAV dùng dòng business_date = D.
{{ asof_latest('sat_account_nav_daily__flex', 'account_hk', business_date=true) }}
