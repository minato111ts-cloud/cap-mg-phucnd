-- Link môi giới - nhóm, grain: một cặp (môi giới, nhóm) từng thấy. Mẫu T-LINK.
-- Hiệu lực theo thời gian ở esat_broker_regrp__flex (driving key broker_hk).
{{ dv_load_link('link_broker_regrp_hk', 'stg_flex__broker', ['broker_hk', 'regrp_hk']) }}
