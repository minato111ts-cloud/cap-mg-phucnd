{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}


{% macro dv_window(col='ingested_ts') -%}
    {%- set lo = var('lo_ts', none) -%}
    {%- set hi = var('hi_ts', none) -%}
    {#- Chỉ dừng lúc thực thi: lúc parse dbt render mọi model không kèm --vars (dbt ls, build staging) -#}
    {%- if (lo is none or hi is none) and execute -%}
        {{ exceptions.raise_compiler_error("Thiếu biến bắt buộc lo_ts hoặc hi_ts cho dv_window()") }}
    {%- endif -%}
    ({{ col }} > '{{ lo }}'::timestamptz and {{ col }} <= '{{ hi }}'::timestamptz)
{%- endmacro %}


{% macro dv_fmt_val(item) -%}
    {%- if item is mapping -%}
        {%- set expr = item['expr'] -%}
        {%- set dtype = item['type'] | lower -%}
    {%- elif item is sequence and item is not string -%}
        {%- set expr = item[0] -%}
        {%- set dtype = item[1] | lower -%}
    {%- else -%}
        {%- set expr = item | string -%}
        {%- set s = expr | lower | trim -%}
        {%- if '::timestamptz' in s or '::timestamp with time zone' in s or s.endswith('_ts') -%}
            {%- set dtype = 'timestamptz' -%}
        {%- elif '::date' in s or s.endswith('_date') or s in ['frdate', 'todate', 'effdate', 'joindate', 'leavedate', 'txdate'] -%}
            {%- set dtype = 'date' -%}
        {%- elif '::bool' in s or s.startswith('is_') or s in ['true', 'false'] -%}
            {%- set dtype = 'boolean' -%}
        {%- else -%}
            {%- set dtype = 'text' -%}
        {%- endif -%}
    {%- endif -%}

    {%- if dtype == 'timestamptz' -%}
        coalesce(to_char(({{ expr }}) at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'), '<NULL>')
    {%- elif dtype == 'date' -%}
        coalesce(to_char(({{ expr }}), 'YYYY-MM-DD'), '<NULL>')
    {%- elif dtype == 'boolean' -%}
        case when ({{ expr }}) is null then '<NULL>' when ({{ expr }}) then 'true' else 'false' end
    {%- else -%}
        coalesce(normalize(({{ expr }})::text, NFC), '<NULL>')
    {%- endif -%}
{%- endmacro %}


{% macro dv_hash(cols) -%}
    {%- if cols is string -%}
        {%- set col_list = [cols] -%}
    {%- else -%}
        {%- set col_list = cols -%}
    {%- endif -%}
    {%- set parts = [] -%}
    {%- for c in col_list -%}
        {%- do parts.append(dv_fmt_val(c)) -%}
    {%- endfor -%}
    sha256(convert_to({{ parts | join(" || '||' || ") }}, 'UTF8'))
{%- endmacro %}
