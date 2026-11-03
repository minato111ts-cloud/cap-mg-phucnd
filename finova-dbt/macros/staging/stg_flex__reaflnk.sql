{#
  Staging flex_reaflnk (phân công chăm sóc). Hai trục thời gian: FRDATE/TODATE là hiệu lực nghiệp vụ,
  ingested_ts là lúc hệ thống biết; staging chỉ chuẩn hóa, không chọn phân công nào hiệu lực
  (DEC-CAP-MG-OVERLAP xử lý ở Business Vault).
#}

{% macro stg_flex__reaflnk_columns() -%}
    bkcc_reaflnk, bk_reaflnk, reaflnk_hk,
    bkcc_broker, bk_broker, broker_hk,
    bkcc_account, bk_account, account_hk,
    link_reaflnk_hk,
    sat_reaflnk_hd,
    autoid, broker_id, afacctno, fr_date, to_date, status, lastchange,
    record_source, source_id, batch_id, ingested_ts, event_ts, record_hash, source_row_no
{%- endmacro %}


{% macro stg_flex__reaflnk_rows() -%}
with parsed as (
    select
        l.source_id, l.batch_id, l.ingested_ts, l.event_ts, l.record_hash, l.source_row_no,
        nullif(btrim(l.autoid), '') as autoid,
        {{ stg_code('l.reacctno') }} as broker_id,
        {{ stg_code('l.afacctno') }} as afacctno,
        {{ stg_code('l.status') }} as status,
        {{ stg_parse_date('l.frdate') }} as fr_date,
        {{ stg_parse_date('l.todate') }} as to_date,
        {{ stg_parse_date('l.lastchange') }} as lastchange
    from {{ source('landing', 'flex_reaflnk') }} l
),

hashed as (
    select
        p.*,
        {{ dv_hash(["'FLEX'", 'autoid']) }} as reaflnk_hk,
        {{ dv_hash(["'FLEX'", 'broker_id']) }} as broker_hk,
        {{ dv_hash(["'FLEX'", 'afacctno']) }} as account_hk,
        {{ dv_hash(["'FLEX'", 'autoid', 'broker_id', 'afacctno']) }} as link_reaflnk_hk,
        {{ dv_hash([
            'broker_id', 'afacctno',
            'fr_date::date', 'to_date::date',
            'status', 'lastchange::date'
        ]) }} as sat_reaflnk_hd
    from parsed p
),

checked as (
    select h.*, {{ stg_batch_dup_cols('autoid', 'sat_reaflnk_hd') }}
    from hashed h
)

select
    'FLEX' as bkcc_reaflnk,
    autoid as bk_reaflnk,
    reaflnk_hk,
    'FLEX' as bkcc_broker,
    broker_id as bk_broker,
    broker_hk,
    'FLEX' as bkcc_account,
    afacctno as bk_account,
    account_hk, link_reaflnk_hk, sat_reaflnk_hd,
    autoid, broker_id, afacctno, fr_date, to_date, status, lastchange,
    'flex.flex_reaflnk' as record_source,
    source_id, batch_id, ingested_ts, event_ts, record_hash, source_row_no,
    case
        when autoid is null or broker_id is null or afacctno is null then 'KEY_NULL'
        when autoid !~ '^[0-9]+$' or broker_id !~ '^BRK[0-9]{3}$' or afacctno !~ '^[0-9]{10}$' then 'KEY_FORMAT'
        -- FRDATE/TODATE dựng nên quan hệ hiệu lực: thiếu hoặc sai là LOAI (DQ-NGAY-SAI cột khóa)
        when fr_date is null or to_date is null then 'INVALID_DATE'
        when to_date < fr_date then 'INVALID_DATE_RANGE'
        when status is null or status not in ('A', 'C') then 'ALLCODE_UNKNOWN'
        when _has_conflict then 'CONFLICT_IN_BATCH'
        when _dup_rank > 1 then 'DUPLICATE_ROW'
    end as reason_code
from checked
{%- endmacro %}
