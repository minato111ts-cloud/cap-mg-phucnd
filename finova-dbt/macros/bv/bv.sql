{#
  Business Vault (T-BV, E.5): PIT và bridge của ngày D là dẫn xuất tất định từ view as-of với cutoff của D.
  pre_hook dùng chung khai ở dbt_project.yml (QT-DAY-REBUILD): asof_session() đặt GUC của D, asof_day_delete() xóa
  phần của D, model chèn lại.
#}


{# Nút ảo UNKNOWN của cây đơn vị (DEC-CAP-MG-ORPHAN): cấp trên thay cho đơn vị cha không tồn tại. Khóa nghiệp vụ
   dành riêng, băm như regrp_hk; không trùng mã thật vì staging chỉ nhận mã dạng HO, CN<số>, G<số> (KEY_FORMAT). #}
{% macro bv_regrp_unknown_bk() -%}
    'UNKNOWN'
{%- endmacro %}

{% macro bv_regrp_unknown_hk() -%}
    {{ dv_hash(["'FLEX'", bv_regrp_unknown_bk()]) }}
{%- endmacro %}
