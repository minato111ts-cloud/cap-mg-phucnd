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
    {%- if lo is none or hi is none -%}
        {{ exceptions.raise_compiler_error("Thiếu biến bắt buộc lo_ts hoặc hi_ts cho dv_window()") }}
    {%- endif -%}
    ({{ col }} > '{{ lo }}'::timestamptz and {{ col }} <= '{{ hi }}'::timestamptz)
{%- endmacro %}


{% macro dv_fmt_val(expr) -%}
    case
        when ({{ expr }}) is null then '<NULL>'
        when pg_typeof({{ expr }})::text = 'timestamp with time zone' then
            to_char(({{ expr }}) at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
        when pg_typeof({{ expr }})::text = 'timestamp without time zone' then
            to_char(({{ expr }}), 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
        when pg_typeof({{ expr }})::text = 'date' then
            to_char(({{ expr }}), 'YYYY-MM-DD')
        when pg_typeof({{ expr }})::text = 'boolean' then
            case when ({{ expr }})::boolean then 'true' else 'false' end
        else
            normalize(({{ expr }})::text, NFC)
    end
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
