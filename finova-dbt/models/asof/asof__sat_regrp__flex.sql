{{ config(alias='sat_regrp__flex') }}
-- Đơn vị as-of D, grain: regrp_hk. Cây ngày D ở BV lấy cạnh từ parentid của view này;
-- đơn vị đã vắng khỏi bản chụp (G7 từ CAP-MG-0032) bị bỏ theo sts_regrp__flex.
{{ asof_latest('sat_regrp__flex', 'regrp_hk', sts_model='sts_regrp__flex') }}
