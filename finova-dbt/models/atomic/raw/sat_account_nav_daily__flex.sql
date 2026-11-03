-- Satellite NAV cuối ngày của tiểu khoản, grain: (account_hk, business_date, ingested_ts). Mẫu T-SAT-DAY.
-- Phiên bản tính trên (tiểu khoản, ngày): bản đính chính NAV ngày cũ thành phiên bản mới của đúng ngày đó.
{{ dv_load_sat_day('account_hk', 'sat_account_nav_hd', 'stg_ref__nav', ['afacctno', 'nav'], business_date='tx_date') }}
