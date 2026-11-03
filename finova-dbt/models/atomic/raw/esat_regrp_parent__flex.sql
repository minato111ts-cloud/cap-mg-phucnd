-- Effectivity satellite của link đơn vị - cha, grain: (link_regrp_parent_hk, ingested_ts). Mẫu T-ESAT-DK.
-- Driving key regrp_hk: đơn vị đổi cha (TH-TAICAUTRUC, vd G4 CN2 -> CN1 ngày 04/05) ghi một dòng đóng, một dòng mở.
{{ dv_load_esat_dk('link_regrp_parent_hk', 'regrp_hk', 'stg_flex__regrp', 'link_regrp_parent') }}
