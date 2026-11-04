{{ config(alias='sat_broker_profile__flex') }}
-- Hồ sơ môi giới as-of D, grain: broker_hk. Người đang mang mã (broker_key, join_date, leave_date)
-- theo DEC-CAP-MG-BROKERKEY, nhóm (grpid) và trạng thái làm việc (DEC-CAP-MG-GAP).
{{ asof_latest('sat_broker_profile__flex', 'broker_hk', sts_model='sts_broker__flex') }}
