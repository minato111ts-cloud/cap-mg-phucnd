{#
  Gold (T-GOLD-DAY, E.8): bảng của ngày D dựng từ Business Vault và view as-of với cutoff của D; pre_hook dùng chung
  khai ở dbt_project.yml. RLS (INV-SEM-RLSDB): policy của database lọc theo người xem, áp cho role đọc
  var('gold_reader_role'); finova_dbt là chủ bảng nên không bị lọc (dbt xóa, ghi, test bình thường).
#}


{# Người xem của phiên: ứng dụng đặt finova.viewer_id (viewer_id trong org_roles). Chưa đặt hoặc rỗng thì NULL,
   policy không khớp dòng nào. #}
{% macro gold_viewer() -%}
    nullif(current_setting('finova.viewer_id', true), '')
{%- endmacro %}


{# Phạm vi của người xem theo org_roles: mã đơn vị hoặc mã môi giới. security definer để role đọc không cần quyền
   trên schema staging; post_hook của dim_broker_org_daily tạo lại mỗi lần build. #}
{% macro gold_viewer_scopes_function() -%}
create or replace function {{ this.schema }}.viewer_scopes() returns text[]
language sql stable security definer set search_path = pg_catalog, pg_temp as $fn$
    select coalesce(array_agg(r.scope order by r.scope), '{}'::text[])
    from {{ ref('ref_org_roles') }} as r
    where r.viewer_id = {{ gold_viewer() }}
$fn$
{%- endmacro %}


{# Bật RLS. Bảng đã bật mà chưa có policy thì role đọc không thấy dòng nào. #}
{% macro gold_rls_enable(relation=none) -%}
    alter table {{ relation or this }} enable row level security
{%- endmacro %}


{# Tạo lại policy đọc của role đọc trên bảng; using là biểu thức trên cột của chính bảng (gọi bảng bằng tên). #}
{% macro gold_rls_policy(relation, using) -%}
drop policy if exists p_viewer on {{ relation }};
create policy p_viewer on {{ relation }} for select to {{ var('gold_reader_role') }} using ({{ using }})
{%- endmacro %}


{# Ngày giao dịch liền trước D theo lịch; NULL nếu D là ngày đầu của lịch. #}
{% macro gold_prev_trading_day() -%}
    (select max(c.calendar_date) from {{ ref('ref_calendar') }} as c
     where c.is_trading_day = 1 and c.calendar_date < {{ asof_var_date() }})
{%- endmacro %}
