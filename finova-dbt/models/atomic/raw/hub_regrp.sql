-- Hub đơn vị (hội sở, chi nhánh, nhóm), grain: một GRPID FLEX. Mẫu T-HUB.
-- Nhận cả mã đơn vị cha và nhóm của môi giới, nên cha không có trong bản chụp (DQ-MOCOI, vd CN9) vẫn có khóa;
-- GT-HUB-NOMASTER đếm các khóa đó.
{{ dv_load_hub('regrp_hk', 'grpid', [
    {'model': 'stg_flex__regrp',  'hk': 'regrp_hk',        'bkcc': 'bkcc_regrp',        'bk': 'bk_regrp'},
    {'model': 'stg_flex__regrp',  'hk': 'parent_regrp_hk', 'bkcc': 'bkcc_parent_regrp', 'bk': 'bk_parent_regrp'},
    {'model': 'stg_flex__broker', 'hk': 'regrp_hk',        'bkcc': 'bkcc_regrp',        'bk': 'bk_regrp'},
]) }}
