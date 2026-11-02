{{ config(tags = ['staging']) }}

-- TC-CAP-MG-EVENTTIME: event_ts > server_ts + ngưỡng thì dùng server_ts và có cờ; trong ngưỡng thì giữ
-- giờ thiết bị, không cờ. Ngưỡng là var('event_future_tolerance_minutes') (customers/ctcka/thresholds.yaml).
-- Thêm vế thứ ba: event_ts của staging phải bằng landing.event_ts do loader tính theo cùng hợp đồng,
-- để hai nơi thực thi quy tắc không lệch nhau.
-- Phép thử âm (Bảng 70): --vars '{"event_future_tolerance_minutes": 14400, ...}' (10 ngày) ->
--   6 sự kiện của lô CAP-MG-0036 mất cờ, và vế thứ ba đỏ vì landing vẫn tính theo ngưỡng 5 phút.

{% set tolerance = var('event_future_tolerance_minutes') %}

select s.batch_id, s.source_row_no, s.event_id, 'FUTURE_NOT_FIXED' as problem
from {{ ref('stg_finova_app__events') }} s
where s.device_event_ts > s.server_ts + interval '{{ tolerance }} minutes'
  and (s.event_ts <> s.server_ts or not s.is_future_ts_fixed)

union all

select s.batch_id, s.source_row_no, s.event_id, 'FIXED_WITHOUT_REASON'
from {{ ref('stg_finova_app__events') }} s
where s.device_event_ts <= s.server_ts + interval '{{ tolerance }} minutes'
  and (s.event_ts <> s.device_event_ts or s.is_future_ts_fixed)

union all

select s.batch_id, s.source_row_no, s.event_id, 'LANDING_EVENT_TS_MISMATCH'
from {{ ref('stg_finova_app__events') }} s
join {{ source('landing', 'finova_app_events') }} l
  on l.batch_id = s.batch_id and l.source_row_no = s.source_row_no
where l.event_ts <> s.event_ts
