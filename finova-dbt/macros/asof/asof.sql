{#
  Tầng as-of (Bảng 20, E.7, Bảng 88): view chỉ trả phiên bản có ingested_ts ≤ cutoff đặt cho phiên.
  Cutoff và ngày D đọc từ GUC finova.asof_cutoff, finova.asof_date qua asof.cutoff(), asof.as_of_date();
  phiên chưa đặt thì báo lỗi, không lấy giờ hiện tại (TC-SLV-NOCUTOFF).
#}


{# Hàm đọc GUC của phiên; gọi ở on-run-start (dbt_project.yml). Chuỗi rỗng cũng là chưa đặt: sau reset,
   current_setting trả '' chứ không trả NULL. #}
{% macro asof_create_function(fn, guc, rtype) -%}
create or replace function asof.{{ fn }}() returns {{ rtype }}
language plpgsql stable as $fn$
declare
    v text := nullif(current_setting('{{ guc }}', true), '');
begin
    if v is null then
        raise exception 'asof.{{ fn }}(): phiên chưa đặt {{ guc }} (TC-SLV-NOCUTOFF)';
    end if;
    return v::{{ rtype }};
end
$fn$
{%- endmacro %}


{# Ngày D của lần chạy: runner truyền as_of_date qua --vars; thiếu thì dừng (KHUNG-VARS). Chỉ dừng lúc thực thi
   vì lúc parse dbt render mọi model không kèm --vars. #}
{% macro asof_var_date() -%}
    {%- set d = var('as_of_date', none) -%}
    {%- if d is none and execute -%}
        {{ exceptions.raise_compiler_error("Thiếu biến bắt buộc as_of_date") }}
    {%- endif -%}
    ('{{ d }}'::date)
{%- endmacro %}


{# cutoff(D) = 00:00 ngày D+1 giờ Việt Nam (mục 2.1), suy từ as_of_date, không lấy giờ chạy. #}
{% macro asof_var_cutoff() -%}
    (({{ asof_var_date() }} + 1)::timestamp at time zone 'Asia/Ho_Chi_Minh')
{%- endmacro %}


{# Đặt mốc của ngày D trên chính connection của model (mẫu gold_day_session, E.8); dùng làm pre_hook cho BV, Gold.
   Cutoff ghi dạng ISO UTC để đọc lại không phụ thuộc TimeZone của phiên. #}
{% macro asof_session() -%}
select set_config('finova.asof_date', to_char({{ asof_var_date() }}, 'YYYY-MM-DD'), false),
       set_config('finova.asof_cutoff',
                  to_char({{ asof_var_cutoff() }} at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), false)
{%- endmacro %}


{# QT-DAY-REBUILD (T-BV, T-GOLD-DAY): pre_hook thứ hai của BV và Gold, xóa phần của ngày D rồi model chèn lại. #}
{% macro asof_day_delete() -%}
    {%- if is_incremental() -%}
        delete from {{ this }} where as_of_date = {{ asof_var_date() }}
    {%- else -%}
        select 1
    {%- endif -%}
{%- endmacro %}


{# Hub, link, nhl (Bảng 88): mọi dòng có ingested_ts ≤ cutoff. #}
{% macro asof_known(model) -%}
select *
from {{ ref(model) }}
where ingested_ts <= (select asof.cutoff())
{%- endmacro %}


{# Satellite (Bảng 88): mỗi khóa lấy phiên bản có ingested_ts lớn nhất ≤ cutoff.
   business_date=true: satellite theo ngày, mỗi (khóa, business_date ≤ D) một phiên bản, trả chuỗi ngày.
   sts_model: nguồn bản chụp đầy đủ; bỏ khóa có trạng thái mới nhất tại cutoff là DELETED (RV-03),
   để view là đúng bản chụp hệ thống biết tại cutoff. #}
{% macro asof_latest(model, key, sts_model=none, business_date=false) -%}
{%- set part = ['s.' ~ key] + (['s.business_date'] if business_date else []) -%}
with v as (
    select distinct on ({{ part | join(', ') }}) s.*
    from {{ ref(model) }} s
    where s.ingested_ts <= (select asof.cutoff())
      {%- if business_date %}
      and s.business_date <= (select asof.as_of_date())
      {%- endif %}
    order by {{ part | join(', ') }}, s.ingested_ts desc
)

select v.*
from v
{%- if sts_model %}
where coalesce((
    select t.status
    from {{ ref(sts_model) }} t
    where t.{{ key }} = v.{{ key }}
      and t.ingested_ts <= (select asof.cutoff())
    order by t.ingested_ts desc
    limit 1
), 'ACTIVE') = 'ACTIVE'
{%- endif %}
{%- endmacro %}
