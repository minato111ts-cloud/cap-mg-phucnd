{#
  Staging finova_app_events. event_ts theo hợp đồng: giờ thiết bị, trừ khi đi trước server_ts quá ngưỡng
  var('event_future_tolerance_minutes') (DQ-TUONGLAI) thì dùng server_ts và gắn cờ. Cùng quy tắc với
  loader (landing.event_ts); test_stg_events_event_time kiểm cả hai khớp nhau.
  Khử trùng (DQ-TRUNG-NGUYEN) chỉ trong một lô: giữ dòng đầu theo source_row_no.
#}

{% macro stg_finova_app__events_columns() -%}
    bkcc_event, bk_event, event_hk,
    bkcc_broker, bk_broker, broker_hk,
    account_hk, nhl_broker_event_hd,
    event_id, broker_id, afacctno, event_type,
    event_ts, device_event_ts, server_ts, event_date, is_future_ts_fixed,
    duration_sec, outcome,
    record_source, source_id, batch_id, ingested_ts, record_hash, source_row_no
{%- endmacro %}


{% macro stg_finova_app__events_rows() -%}
{%- set tolerance = var('event_future_tolerance_minutes') -%}
with parsed as (
    select
        l.source_id, l.batch_id, l.ingested_ts, l.event_ts as landing_event_ts, l.record_hash, l.source_row_no,
        nullif(lower(btrim(l.event_id)), '') as event_id,
        {{ stg_code('l.broker_id') }} as broker_id,
        {{ stg_code('l.afacctno') }} as afacctno,
        {{ stg_code('l.event_type') }} as event_type,
        {{ stg_parse_ts('l.raw_event_ts') }} as device_event_ts,
        {{ stg_parse_ts('l.server_ts') }} as server_ts,
        {{ stg_parse_int('l.duration_sec') }} as duration_sec,
        {{ stg_code('l.outcome') }} as outcome
    from {{ source('landing', 'finova_app_events') }} l
),

timed as (
    select
        p.*,
        coalesce(p.device_event_ts > p.server_ts + interval '{{ tolerance }} minutes', false) as is_future_ts_fixed,
        case
            when p.device_event_ts > p.server_ts + interval '{{ tolerance }} minutes' then p.server_ts
            else coalesce(p.device_event_ts, p.server_ts)
        end as event_ts
    from parsed p
),

hashed as (
    select
        t.*,
        {{ dv_hash(["'FINOVA_APP'", 'event_id']) }} as event_hk,
        {{ dv_hash(["'FLEX'", 'broker_id']) }} as broker_hk,
        {{ dv_hash(["'FLEX'", 'afacctno']) }} as account_hk,
        -- nội dung của non-historized link sự kiện (GT-NHL-CONTENT); giờ thiết bị gốc để phát hiện gửi lại khác nội dung
        {{ dv_hash([
            'broker_id', 'afacctno', 'event_type',
            'device_event_ts', 'server_ts',
            {'expr': 'duration_sec', 'type': 'text'}, 'outcome'
        ]) }} as nhl_broker_event_hd
    from timed t
),

checked as (
    select h.*, {{ stg_batch_dup_cols('event_id', 'nhl_broker_event_hd') }}
    from hashed h
)

select
    'FINOVA_APP' as bkcc_event,
    c.event_id as bk_event,
    c.event_hk,
    'FLEX' as bkcc_broker,
    c.broker_id as bk_broker,
    c.broker_hk, c.account_hk, c.nhl_broker_event_hd,
    c.event_id, c.broker_id, c.afacctno, c.event_type,
    c.event_ts, c.device_event_ts, c.server_ts,
    (c.event_ts at time zone 'Asia/Ho_Chi_Minh')::date as event_date,
    c.is_future_ts_fixed,
    c.duration_sec, c.outcome,
    'finova_app.finova_app_events' as record_source,
    c.source_id, c.batch_id, c.ingested_ts, c.record_hash, c.source_row_no,
    case
        when c.event_id is null or c.broker_id is null or c.afacctno is null then 'KEY_NULL'
        when c.event_id !~ '^[0-9a-f-]{36}$' or c.broker_id !~ '^BRK[0-9]{3}$' or c.afacctno !~ '^[0-9]{10}$' then 'KEY_FORMAT'
        when et.event_type is null then 'ALLCODE_UNKNOWN'
        when c.event_ts is null then 'INVALID_TIMESTAMP'
        when c._has_conflict then 'CONFLICT_IN_BATCH'
        when c._dup_rank > 1 then 'DUPLICATE_EVENT'
    end as reason_code
from checked c
left join {{ ref('ref_event_type') }} et on et.event_type = c.event_type
{%- endmacro %}
