{{ config(tags = ['staging']) }}

-- GT-STG-PII: cột trong pii_columns của hợp đồng (flex_broker: FULLNAME, EMAIL, MOBILE;
-- manual_kpi: fullname) không được ra khỏi staging ở dạng rõ. Staging chỉ xuất bản đã che
-- (email_masked, mobile_masked); giá trị gốc chỉ đi vào hash_diff (một chiều).
-- Phép thử âm: thêm `mobile` vào stg_flex__broker_columns() -> test đỏ.

{% set pii_columns = ['fullname', 'email', 'mobile', 'raw_fullname', 'raw_email', 'raw_mobile'] %}

select table_name, column_name, 'PII_COLUMN_EXPOSED' as problem
from information_schema.columns
where table_schema = 'staging'
  and table_name like 'stg\_%'
  and lower(column_name) in ({% for c in pii_columns %}'{{ c }}'{% if not loop.last %}, {% endif %}{% endfor %})

union all

select 'stg_flex__broker', 'mobile_masked', 'MOBILE_NOT_MASKED'
from {{ ref('stg_flex__broker') }}
where mobile_masked is not null and mobile_masked !~ '^\*+[0-9]{0,4}$'

union all

select 'stg_flex__broker', 'email_masked', 'EMAIL_NOT_MASKED'
from {{ ref('stg_flex__broker') }}
where email_masked is not null and email_masked !~ '^.\*\*\*@'
