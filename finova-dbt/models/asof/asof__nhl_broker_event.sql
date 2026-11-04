{{ config(alias='nhl_broker_event') }}
-- Sự kiện tương tác as-of D, grain: nhl_broker_event_hk. Số tương tác 30 ngày, COVER30, số cuộc gọi lũy kế quý.
-- Không có sts: sự kiện bất biến, không bị xóa.
{{ asof_known('nhl_broker_event') }}
