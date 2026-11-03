-- Link phân công - môi giới - tiểu khoản, grain: một bộ (AUTOID, môi giới, tiểu khoản). Mẫu T-LINK.
-- Hiệu lực nghiệp vụ [fr_date, to_date] ở sat_reaflnk__flex; chọn phân công khi chồng lấn ở Business Vault.
{{ dv_load_link('link_reaflnk_hk', 'stg_flex__reaflnk', ['reaflnk_hk', 'broker_hk', 'account_hk']) }}
