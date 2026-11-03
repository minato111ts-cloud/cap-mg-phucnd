-- Hub phân công chăm sóc, grain: một REAFLNK.AUTOID FLEX. Mẫu T-HUB.
-- DEC-MG-B2: dòng phân công còn đổi (TODATE đóng sau) nên mô hình bằng hub (Q5); quan hệ ở link_reaflnk.
{{ dv_load_hub('reaflnk_hk', 'autoid', [
    {'model': 'stg_flex__reaflnk', 'hk': 'reaflnk_hk', 'bkcc': 'bkcc_reaflnk', 'bk': 'bk_reaflnk'},
]) }}
