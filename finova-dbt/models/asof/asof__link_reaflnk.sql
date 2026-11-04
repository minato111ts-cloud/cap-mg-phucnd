{{ config(alias='link_reaflnk') }}
-- Link phân công - môi giới - tiểu khoản as-of D, grain: link_reaflnk_hk. Nối phân công với broker_hk,
-- account_hk để ghép với NAV và sự kiện.
{{ asof_known('link_reaflnk') }}
