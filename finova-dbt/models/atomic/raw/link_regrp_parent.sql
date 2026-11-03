-- Link đơn vị - đơn vị cha, grain: một cặp (đơn vị, cha) từng thấy. Mẫu T-LINK.
-- Hiệu lực ở esat_regrp_parent__flex (driving key regrp_hk); dòng tạo vòng đã bị loại ở staging (DEC-CAP-MG-CYCLE).
{{ dv_load_link('link_regrp_parent_hk', 'stg_flex__regrp', ['regrp_hk', 'parent_regrp_hk']) }}
