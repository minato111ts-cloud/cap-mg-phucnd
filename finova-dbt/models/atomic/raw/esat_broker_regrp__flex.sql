-- Effectivity satellite của link môi giới - nhóm, grain: (link_broker_regrp_hk, ingested_ts). Mẫu T-ESAT-DK.
-- Driving key broker_hk: môi giới chuyển nhóm thì đóng link cũ, mở link mới cùng ingested_ts (Q4).
{{ dv_load_esat_dk('link_broker_regrp_hk', 'broker_hk', 'stg_flex__broker', 'link_broker_regrp') }}
