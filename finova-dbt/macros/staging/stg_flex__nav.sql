{#
  Staging ref_nav. NAV là thuộc tính theo ngày của tiểu khoản: satellite trên hub tiểu khoản
  khóa (account_hk, tx_date), không phải một hub riêng.
#}

{% macro stg_flex__nav_columns() -%}
    bkcc_account, bk_account, account_hk,
    sat_account_nav_hd,
    tx_date, afacctno, nav,
    record_source, source_id, batch_id, ingested_ts, event_ts, record_hash, source_row_no
{%- endmacro %}


{% macro stg_flex__nav_rows() -%}
with parsed as (
    select
        l.source_id, l.batch_id, l.ingested_ts, l.event_ts, l.record_hash, l.source_row_no,
        nullif(btrim(l.txdate), '') is null as _txdate_empty,
        {{ stg_parse_date('l.txdate') }} as tx_date,
        {{ stg_code('l.afacctno') }} as afacctno,
        nullif(btrim(l.nav), '') is null as _nav_empty,
        -- hợp đồng: file hệ thống dùng dấu chấm thập phân; dấu phẩy là phân cách nghìn
        {{ stg_parse_number('l.nav', '.') }}::numeric(20, 4) as nav
    from {{ source('landing', 'ref_nav') }} l
),

hashed as (
    select
        p.*,
        {{ dv_hash(["'FLEX'", 'afacctno']) }} as account_hk,
        {{ dv_hash([{'expr': 'nav', 'type': 'text'}]) }} as sat_account_nav_hd
    from parsed p
),

checked as (
    select h.*, {{ stg_batch_dup_cols("afacctno, tx_date", 'sat_account_nav_hd') }}
    from hashed h
)

select
    'FLEX' as bkcc_account,
    afacctno as bk_account,
    account_hk, sat_account_nav_hd,
    tx_date, afacctno, nav,
    'flex.ref_nav' as record_source,
    source_id, batch_id, ingested_ts, event_ts, record_hash, source_row_no,
    case
        when _txdate_empty or afacctno is null then 'KEY_NULL'
        when tx_date is null then 'INVALID_DATE'
        when afacctno !~ '^[0-9]{10}$' then 'KEY_FORMAT'
        when _nav_empty or nav is null then 'INVALID_NUMERIC'
        when _has_conflict then 'CONFLICT_IN_BATCH'
        when _dup_rank > 1 then 'DUPLICATE_ROW'
    end as reason_code
from checked
{%- endmacro %}
