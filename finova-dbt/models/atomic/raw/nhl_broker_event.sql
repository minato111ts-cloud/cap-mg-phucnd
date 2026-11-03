-- Non-historized link sự kiện tương tác môi giới - tiểu khoản, grain: một event_id. Mẫu T-NHL.
-- Sự kiện bất biến (Q5): chèn khóa mới, giữ lần thấy đầu; gửi lại khác nội dung do GT-NHL-CONTENT chặn ở staging.
{{ dv_load_nhl('nhl_broker_event_hk', 'nhl_broker_event_hd', 'stg_finova_app__events', [
    'broker_hk', 'account_hk', 'event_id', 'event_type',
    'event_ts', 'device_event_ts', 'server_ts', 'event_date',
    'is_future_ts_fixed', 'is_device_ts_invalid', 'duration_sec', 'outcome',
]) }}
