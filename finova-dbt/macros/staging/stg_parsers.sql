{#
  Ép kiểu có kiểm cho staging (luật cứng). Mọi macro trả NULL khi giá trị không hợp lệ thay vì làm lỗi
  cả view: một ô '31/02/2026' hay '1,5x' không được làm sập staging của mọi lô. Dòng có NULL do ép kiểu
  hỏng được phân loại ở model (cột khóa: loại; cột thuộc tính: nhận và test warn đếm).
  CASE lồng nhau để PostgreSQL chỉ gọi make_date / ::numeric sau khi đã qua kiểm tra.
#}

{% macro stg_parse_date(col) -%}
(case
    when btrim({{ col }}) ~ '^[0-9]{2}/[0-9]{2}/[0-9]{4}$'
        then {{ stg_make_date_from_parts("substr(btrim(" ~ col ~ "), 7, 4)", "substr(btrim(" ~ col ~ "), 4, 2)", "substr(btrim(" ~ col ~ "), 1, 2)") }}
    when btrim({{ col }}) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
        then {{ stg_make_date_from_parts("substr(btrim(" ~ col ~ "), 1, 4)", "substr(btrim(" ~ col ~ "), 6, 2)", "substr(btrim(" ~ col ~ "), 9, 2)") }}
end)
{%- endmacro %}


{% macro stg_make_date_from_parts(y, m, d) -%}
case when ({{ m }})::int between 1 and 12 and ({{ y }})::int >= 1 then
    case when ({{ d }})::int between 1 and extract(day from make_date(({{ y }})::int, ({{ m }})::int, 1) + interval '1 month' - interval '1 day')::int
        then make_date(({{ y }})::int, ({{ m }})::int, ({{ d }})::int)
    end
end
{%- endmacro %}


{#
  ISO-8601 có giờ. Có offset (Z, +07:00) thì ép thẳng nên không phụ thuộc TimeZone của phiên;
  thiếu offset thì hiểu là giờ Việt Nam (+07:00), cùng quy tắc với loader (parse_iso_timestamptz).
#}
{% macro stg_parse_ts(col) -%}
(case
    when btrim({{ col }}) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}[T ]([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\.[0-9]{1,6})?(Z|[+-][0-9]{2}(:?[0-9]{2})?)?$'
        then case when {{ stg_parse_date("substr(btrim(" ~ col ~ "), 1, 10)") }} is not null then
            (btrim({{ col }})
             || case when btrim({{ col }}) ~ '(Z|[+-][0-9]{2}(:?[0-9]{2})?)$' then '' else '+07:00' end)::timestamptz
        end
end)
{%- endmacro %}


{#
  Số có thể ghi dạng chữ với dấu phân cách (DQ-SO-DINHDANG, DQ-EXCEL).
  decimal_sep=',' (kiểu Việt Nam, file Excel nhập tay): '1.200' = 1200, '10,5' = 10.5.
  decimal_sep='.' (kiểu file hệ thống): '1,500,000' = 1500000, '25.5' = 25.5.
  Hợp đồng nguồn khai dấu thập phân của từng cột vì '1,500' không tự phân biệt được.
#}
{% macro stg_parse_number(col, decimal_sep='.') -%}
{%- set s = "regexp_replace(btrim(" ~ col ~ "), '\\s', '', 'g')" -%}
{%- if decimal_sep == ',' -%}
(case
    when {{ s }} ~ '^-?([0-9]{1,3}(\.[0-9]{3})+|[0-9]+)(,[0-9]+)?$'
        then replace(replace({{ s }}, '.', ''), ',', '.')::numeric
end)
{%- else -%}
(case
    when {{ s }} ~ '^-?([0-9]{1,3}(,[0-9]{3})+|[0-9]+)(\.[0-9]+)?$'
        then replace({{ s }}, ',', '')::numeric
end)
{%- endif -%}
{%- endmacro %}


{% macro stg_parse_int(col, decimal_sep='.') -%}
(case when {{ stg_parse_number(col, decimal_sep) }} = trunc({{ stg_parse_number(col, decimal_sep) }})
    then {{ stg_parse_number(col, decimal_sep) }}::bigint
end)
{%- endmacro %}


{# Ô lỗi công thức của Excel (DQ-CONGTHUC) #}
{% macro stg_is_excel_error(col) -%}
coalesce(btrim({{ col }}) ~* '^#(REF!|DIV/0!|VALUE!|NAME\?|N/A|NUM!|NULL!)$', false)
{%- endmacro %}


{# Chuẩn hóa mã: trim + viết hoa, rỗng thành NULL (DQ-KHOA-CASE) #}
{% macro stg_code(col) -%}
nullif(upper(btrim({{ col }})), '')
{%- endmacro %}


{# Che dữ liệu định danh (GT-STG-PII): chỉ giữ 4 số cuối điện thoại, ký tự đầu và tên miền của email #}
{% macro stg_mask_mobile(col) -%}
case when nullif(btrim({{ col }}), '') is not null
    then repeat('*', greatest(length(btrim({{ col }})) - 4, 0)) || right(btrim({{ col }}), 4)
end
{%- endmacro %}

{% macro stg_mask_email(col) -%}
case when btrim({{ col }}) ~ '^[^@]+@[^@]+$'
    then left(btrim({{ col }}), 1) || '***' || substr(btrim({{ col }}), strpos(btrim({{ col }}), '@'))
end
{%- endmacro %}


{#
  Một dòng trong lô: cùng khóa, cùng hash nội dung -> dòng lặp (DQ-TRUNG-NGUYEN, SUA: giữ dòng đầu);
  cùng khóa, khác hash nội dung -> xung đột (DQ-TRUNG-XUNGDOT, LOAI mọi dòng của khóa đó).
  Chỉ xét trong một lô (batch_id): lô khác nhau là các lần thấy khác nhau, vault tự giữ lần thấy đầu.
#}
{% macro stg_batch_dup_cols(key_expr, hd_col) -%}
row_number() over (partition by batch_id, {{ key_expr }} order by source_row_no) as _dup_rank,
min(encode({{ hd_col }}, 'hex')) over (partition by batch_id, {{ key_expr }})
    <> max(encode({{ hd_col }}, 'hex')) over (partition by batch_id, {{ key_expr }}) as _has_conflict
{%- endmacro %}
