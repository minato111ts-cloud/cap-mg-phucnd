{#
  Staging manual_kpi (file Excel nhập tay). Landing giữ nguyên văn từng ô; staging đổi số dạng chữ
  kiểu Việt Nam ('10,5', '1.200') thành số (DQ-EXCEL), loại dòng có ô lỗi công thức (DQ-CONGTHUC) và
  dòng chưa duyệt (DQ-CHUADUYET). Chỉ tiêu là satellite trên hub môi giới, không phải hub riêng.
#}

{% macro stg_manual__kpi_columns() -%}
    bkcc_broker, bk_broker, broker_hk,
    sat_broker_kpi_hd,
    broker_id, target_new_clients, target_calls, target_aum_bil, approver, approved_date,
    excel_row_no, source_col_map,
    record_source, source_id, batch_id, ingested_ts, event_ts, record_hash, source_row_no
{%- endmacro %}


{% macro stg_manual__kpi_rows() -%}
with parsed as (
    select
        l.source_id, l.batch_id, l.ingested_ts, l.event_ts, l.record_hash, l.source_row_no,
        l.excel_row_no, l.source_col_map,
        {{ stg_code('l.broker_id') }} as broker_id,
        {{ stg_is_excel_error('l.target_new_clients') }}
            or {{ stg_is_excel_error('l.target_calls') }}
            or {{ stg_is_excel_error('l.target_aum_bil') }}
            or {{ stg_is_excel_error('l.approver') }}
            or {{ stg_is_excel_error('l.approved_date') }} as _formula_error,
        -- hợp đồng: file nhập tay dùng dấu phẩy thập phân, dấu chấm phân cách nghìn
        {{ stg_parse_int('l.target_new_clients', ',') }} as target_new_clients,
        {{ stg_parse_int('l.target_calls', ',') }} as target_calls,
        {{ stg_parse_number('l.target_aum_bil', ',') }}::numeric(20, 4) as target_aum_bil,
        nullif(btrim(l.approver), '') as approver,
        {{ stg_parse_date('l.approved_date') }} as approved_date
    from {{ source('landing', 'manual_kpi') }} l
),

hashed as (
    select
        p.*,
        {{ dv_hash(["'FLEX'", 'broker_id']) }} as broker_hk,
        {{ dv_hash([
            {'expr': 'target_new_clients', 'type': 'text'},
            {'expr': 'target_calls', 'type': 'text'},
            {'expr': 'target_aum_bil', 'type': 'text'},
            'approver', 'approved_date::date'
        ]) }} as sat_broker_kpi_hd
    from parsed p
),

checked as (
    select h.*, {{ stg_batch_dup_cols('broker_id', 'sat_broker_kpi_hd') }}
    from hashed h
)

select
    'FLEX' as bkcc_broker,
    broker_id as bk_broker,
    broker_hk, sat_broker_kpi_hd,
    broker_id, target_new_clients, target_calls, target_aum_bil, approver, approved_date,
    excel_row_no, source_col_map,
    'manual.manual_kpi' as record_source,
    source_id, batch_id, ingested_ts, event_ts, record_hash, source_row_no,
    case
        when _formula_error then 'FORMULA_ERROR'
        when broker_id is null then 'KEY_NULL'
        when broker_id !~ '^BRK[0-9]{3}$' then 'KEY_FORMAT'
        when approver is null or approved_date is null then 'UNAPPROVED_ROW'
        when target_new_clients is null or target_calls is null or target_aum_bil is null then 'INVALID_NUMERIC'
        when _has_conflict then 'CONFLICT_IN_BATCH'
        when _dup_rank > 1 then 'DUPLICATE_ROW'
    end as reason_code
from checked
{%- endmacro %}
