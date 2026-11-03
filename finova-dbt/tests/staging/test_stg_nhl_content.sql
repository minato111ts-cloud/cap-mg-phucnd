{{ config(tags = ['staging']) }}

-- GT-NHL-CONTENT (Bảng 85): các dòng staging hợp lệ cùng khóa nhl có cùng nội dung, xét trên MỌI lô.
-- T-NHL chỉ chèn khóa chưa có và không so nội dung, nên sự kiện gửi lại ở lô sau với nội dung khác
-- sẽ bị raw vault bỏ qua im lặng; test này là chỗ duy nhất phát hiện.
-- Phép thử âm (DB thử): chèn lô mới gửi lại một event_id đã có, đổi duration_sec -> test đỏ 1 khóa.

select nhl_broker_event_hk, min(event_id) as event_id, count(distinct nhl_broker_event_hd) as hd_versions
from {{ ref('stg_finova_app__events') }}
group by nhl_broker_event_hk
having count(distinct nhl_broker_event_hd) > 1
