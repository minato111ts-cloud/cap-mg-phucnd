-- Hub môi giới, grain: một mã môi giới FLEX (broker_hk = dv_hash('FLEX', broker_id)). Mẫu T-HUB.
-- DEC-CAP-MG-BROKERKEY PA A: mã nguồn làm khóa; người mang mã tách ở sat_broker_profile__flex (join_date).
-- Nạp từ mọi staging mang mã môi giới (DEC-ELT-HUBSRC), nên link và nhl không trỏ tới khóa vắng mặt.
{{ dv_load_hub('broker_hk', 'broker_id', [
    {'model': 'stg_flex__broker',       'hk': 'broker_hk', 'bkcc': 'bkcc_broker', 'bk': 'bk_broker'},
    {'model': 'stg_flex__reaflnk',      'hk': 'broker_hk', 'bkcc': 'bkcc_broker', 'bk': 'bk_broker'},
    {'model': 'stg_finova_app__events', 'hk': 'broker_hk', 'bkcc': 'bkcc_broker', 'bk': 'bk_broker'},
    {'model': 'stg_manual__kpi',        'hk': 'broker_hk', 'bkcc': 'bkcc_broker', 'bk': 'bk_broker'},
]) }}
