-- Hub tiểu khoản, grain: một AFACCTNO FLEX. Mẫu T-HUB.
-- Đề CAP-MG không có nguồn chủ của tiểu khoản (AFMAST), nên hub nhận khóa từ phân công, NAV và sự kiện.
{{ dv_load_hub('account_hk', 'afacctno', [
    {'model': 'stg_flex__reaflnk',      'hk': 'account_hk', 'bkcc': 'bkcc_account', 'bk': 'bk_account'},
    {'model': 'stg_ref__nav',           'hk': 'account_hk', 'bkcc': 'bkcc_account', 'bk': 'bk_account'},
    {'model': 'stg_finova_app__events', 'hk': 'account_hk', 'bkcc': 'bkcc_account', 'bk': 'bk_account'},
]) }}
