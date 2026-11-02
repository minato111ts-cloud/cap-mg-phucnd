{#
  Staging flex_broker. View hợp lệ và view __rejected cùng gọi stg_flex__broker_rows(): phân loại lỗi
  chỉ viết một lần nên hai view không thể lệch nhau, và GT-STG-RECON cân theo cấu tạo.
#}

{% macro stg_flex__broker_columns() -%}
    bkcc_broker, bk_broker, broker_hk,
    regrp_hk, broker_regrp_link_hk,
    sat_broker_profile_hd,
    broker_id, join_date, leave_date, broker_key, grpid, status,
    email_masked, mobile_masked,
    record_source, source_id, batch_id, ingested_ts, event_ts, record_hash, source_row_no
{%- endmacro %}


{% macro stg_flex__broker_rows() -%}
with parsed as (
    select
        l.source_id, l.batch_id, l.ingested_ts, l.event_ts, l.record_hash, l.source_row_no,
        {{ stg_code('l.brokerid') }} as broker_id,
        {{ stg_code('l.grpid') }} as grpid,
        {{ stg_code('l.status') }} as status,
        nullif(btrim(l.fullname), '') as fullname,
        nullif(btrim(l.email), '') as email,
        nullif(btrim(l.mobile), '') as mobile,
        {{ stg_parse_date('l.joindate') }} as join_date,
        {{ stg_parse_date('l.leavedate') }} as leave_date
    from {{ source('landing', 'flex_broker') }} l
),

hashed as (
    select
        p.*,
        -- DEC-CAP-MG-BROKERKEY (PA A): hub môi giới khóa theo ('FLEX', BROKERID), cùng công thức ở mọi staging
        {{ dv_hash(["'FLEX'", 'broker_id']) }} as broker_hk,
        case when grpid is not null then {{ dv_hash(["'FLEX'", 'grpid']) }} end as regrp_hk,
        case when grpid is not null then {{ dv_hash(["'FLEX'", 'broker_id', 'grpid']) }} end as broker_regrp_link_hk,
        -- JOINDATE trong hashdiff: mã cấp lại cho người mới thì satellite sinh phiên bản mới.
        -- fullname/email/mobile chỉ đi vào hash (một chiều), không ra cột rõ (GT-STG-PII)
        {{ dv_hash([
            'fullname', 'email', 'mobile', 'grpid',
            'join_date::date', 'leave_date::date', 'status'
        ]) }} as sat_broker_profile_hd
    from parsed p
),

checked as (
    select h.*, {{ stg_batch_dup_cols('broker_id', 'sat_broker_profile_hd') }}
    from hashed h
)

select
    'FLEX' as bkcc_broker,
    broker_id as bk_broker,
    broker_hk, regrp_hk, broker_regrp_link_hk, sat_broker_profile_hd,
    broker_id, join_date, leave_date,
    -- Khóa người (mã + ngày vào làm): thuộc tính để Business Vault/Gold tách người, không phải khóa hub
    broker_id || ':' || to_char(join_date, 'YYYY-MM-DD') as broker_key,
    grpid, status,
    {{ stg_mask_email('email') }} as email_masked,
    {{ stg_mask_mobile('mobile') }} as mobile_masked,
    'flex.flex_broker' as record_source,
    source_id, batch_id, ingested_ts, event_ts, record_hash, source_row_no,
    case
        when broker_id is null then 'KEY_NULL'
        when broker_id !~ '^BRK[0-9]{3}$' then 'KEY_FORMAT'
        when status is null or status not in ('A', 'C') then 'ALLCODE_UNKNOWN'
        when _has_conflict then 'CONFLICT_IN_BATCH'
        when _dup_rank > 1 then 'DUPLICATE_ROW'
    end as reason_code
from checked
{%- endmacro %}
