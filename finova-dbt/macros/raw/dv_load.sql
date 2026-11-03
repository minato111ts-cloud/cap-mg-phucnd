{#
  Mẫu nạp raw vault (E.5, Bảng 83): T-HUB, T-LINK, T-NHL, T-SAT, T-SAT-DAY, T-ESAT-DK và T-STS cho bản chụp đầy đủ.
  Mọi mẫu chỉ đọc staging trong cửa sổ (lo_ts, hi_ts] qua dv_window() (KT-03) và chỉ đọc {{ this }} khi incremental.
  Khác SQL mẫu của đề một điểm: dòng đầu cửa sổ so với phiên bản trong vault NGAY TRƯỚC ingested_ts của nó
  (không phải phiên bản mới nhất), và bỏ qua (khóa, ingested_ts) đã có, để chạy lại cửa sổ cũ không thêm dòng (PT-IDEMP).
#}


{# T-HUB: hợp khóa từ mọi staging mang khóa, chèn khóa chưa có; giữ ingested_ts, event_ts, record_source của lần thấy đầu.
   sources: danh sách {model, hk, bkcc, bk} theo tên cột ở staging. #}
{% macro dv_load_hub(hk, bk, sources) -%}
with w as (
    {%- for s in sources %}
    select {{ s.hk }} as {{ hk }}, {{ s.bkcc }} as bkcc, {{ s.bk }} as {{ bk }},
           ingested_ts, event_ts, record_source
    from {{ ref(s.model) }}
    where {{ dv_window('ingested_ts') }}
      and {{ s.hk }} is not null
    {%- if not loop.last %}
    union all
    {%- endif %}
    {%- endfor %}
)
select distinct on (w.{{ hk }})
       w.{{ hk }}, w.bkcc, w.{{ bk }}, w.ingested_ts, w.event_ts, w.record_source
from w
{%- if is_incremental() %}
where not exists (select 1 from {{ this }} t where t.{{ hk }} = w.{{ hk }})
{%- endif %}
order by w.{{ hk }}, w.ingested_ts, w.record_source, w.event_ts
{%- endmacro %}


{# T-LINK: như T-HUB trên link_hk; cols là khóa hub (và khóa phụ thuộc nếu có), không có thuộc tính. #}
{% macro dv_load_link(link_hk, model, cols) -%}
with w as (
    select {{ link_hk }}, {{ cols | join(', ') }}, ingested_ts, event_ts, record_source
    from {{ ref(model) }}
    where {{ dv_window('ingested_ts') }}
      and {{ link_hk }} is not null
)
select distinct on (w.{{ link_hk }})
       w.{{ link_hk }}, {% for c in cols %}w.{{ c }}, {% endfor %}w.ingested_ts, w.event_ts, w.record_source
from w
{%- if is_incremental() %}
where not exists (select 1 from {{ this }} t where t.{{ link_hk }} = w.{{ link_hk }})
{%- endif %}
order by w.{{ link_hk }}, w.ingested_ts, w.record_source, w.event_ts
{%- endmacro %}


{# T-NHL: sự kiện bất biến, chỉ chèn khóa mới, không so nội dung (xung đột nội dung do GT-NHL-CONTENT ở staging chặn). #}
{% macro dv_load_nhl(hk, hd, model, cols) -%}
select distinct on (w.{{ hk }})
       w.{{ hk }}, {% for c in cols %}w.{{ c }}, {% endfor %}w.{{ hd }} as hash_diff,
       w.ingested_ts, w.record_source
from {{ ref(model) }} w
where {{ dv_window('w.ingested_ts') }}
  and w.{{ hk }} is not null
{%- if is_incremental() %}
  and not exists (select 1 from {{ this }} t where t.{{ hk }} = w.{{ hk }})
{%- endif %}
order by w.{{ hk }}, w.ingested_ts, w.record_source
{%- endmacro %}


{# T-SAT (business_date = none) và T-SAT-DAY (business_date là biểu thức cột ngày nghiệp vụ):
   ghi phiên bản khi hash_diff khác phiên bản liền trước của cùng khóa (cùng khóa và ngày với T-SAT-DAY), INV-T3.
   attrs: danh sách cột thuộc tính lấy nguyên tên từ staging. #}
{% macro dv_load_sat(parent_hk, hd, model, attrs, business_date=none) -%}
{%- set part = [parent_hk] + (['business_date'] if business_date else []) -%}
with w as (
    select {{ parent_hk }},
           {%- if business_date %} {{ business_date }} as business_date,{% endif %}
           ingested_ts, event_ts, {{ hd }} as hash_diff, record_source,
           {{ attrs | join(', ') }}
    from {{ ref(model) }}
    where {{ dv_window('ingested_ts') }}
      and {{ parent_hk }} is not null
),

-- bỏ dòng trùng nguyên nội dung cùng thời điểm; trùng khóa mà khác nội dung đã bị GT-STG-KEYTS chặn
v as (
    select distinct on ({{ part | join(', ') }}, ingested_ts, hash_diff) *
    from w
    order by {{ part | join(', ') }}, ingested_ts, hash_diff, event_ts
),

seq as (
    select v.*,
           lag(v.hash_diff) over (partition by {{ part | join(', ') }} order by v.ingested_ts) as prev_hd,
           row_number() over (partition by {{ part | join(', ') }} order by v.ingested_ts) as rn
    from v
)

select seq.{{ parent_hk }},
       {%- if business_date %} seq.business_date,{% endif %}
       seq.ingested_ts, seq.event_ts, seq.hash_diff, seq.record_source,
       {% for a in attrs %}seq.{{ a }}{% if not loop.last %}, {% endif %}{% endfor %}
from seq
{%- if is_incremental() %}
-- phiên bản trong vault ngay trước dòng đầu cửa sổ của từng khóa
left join lateral (
    select t.hash_diff
    from {{ this }} t
    where t.{{ parent_hk }} = seq.{{ parent_hk }}
      {%- if business_date %}
      and t.business_date = seq.business_date
      {%- endif %}
      and t.ingested_ts < seq.ingested_ts
    order by t.ingested_ts desc
    limit 1
) cur on seq.rn = 1
where seq.hash_diff is distinct from coalesce(seq.prev_hd, cur.hash_diff)
  and not exists (
      select 1 from {{ this }} t
      where t.{{ parent_hk }} = seq.{{ parent_hk }}
        {%- if business_date %}
        and t.business_date = seq.business_date
        {%- endif %}
        and t.ingested_ts = seq.ingested_ts
  )
{%- else %}
where seq.hash_diff is distinct from seq.prev_hd
{%- endif %}
{%- endmacro %}


{% macro dv_load_sat_day(parent_hk, hd, model, attrs, business_date) -%}
{{ dv_load_sat(parent_hk, hd, model, attrs, business_date=business_date) }}
{%- endmacro %}


{# T-ESAT-DK: effectivity suy từ driving key. Driving key trỏ sang link khác thì ghi is_active = false cho link cũ
   và true cho link mới, cùng ingested_ts. link_model là link đích (đã có cột driving_key). #}
{% macro dv_load_esat_dk(link_hk, driving_key, model, link_model) -%}
{#- ref ngoài khối is_incremental() để dbt thấy phụ thuộc vào link lúc parse -#}
{%- set link_rel = ref(link_model) -%}
with w as (
    select {{ driving_key }}, {{ link_hk }}, ingested_ts, event_ts, record_source
    from {{ ref(model) }}
    where {{ dv_window('ingested_ts') }}
      and {{ link_hk }} is not null
),

-- một link mỗi (driving key, thời điểm); staging đã loại xung đột trong cùng ingested_ts
v as (
    select distinct on ({{ driving_key }}, ingested_ts) *
    from w
    order by {{ driving_key }}, ingested_ts, {{ link_hk }}
),

seq as (
    select v.*,
           lag(v.{{ link_hk }}) over (partition by v.{{ driving_key }} order by v.ingested_ts) as prev_link,
           row_number() over (partition by v.{{ driving_key }} order by v.ingested_ts) as rn
    from v
),

chg as (
    select seq.*,
           coalesce(seq.prev_link{% if is_incremental() %}, cur.{{ link_hk }}{% endif %}) as old_link
    from seq
    {%- if is_incremental() %}
    -- link đang hiệu lực của driving key ngay trước dòng đầu cửa sổ
    left join lateral (
        select x.{{ link_hk }}
        from (
            select distinct on (e.{{ link_hk }}) e.{{ link_hk }}, e.is_active
            from {{ this }} e
            join {{ link_rel }} l on l.{{ link_hk }} = e.{{ link_hk }}
            where l.{{ driving_key }} = seq.{{ driving_key }}
              and e.ingested_ts < seq.ingested_ts
            order by e.{{ link_hk }}, e.ingested_ts desc
        ) x
        where x.is_active
        order by x.{{ link_hk }}
        limit 1
    ) cur on seq.rn = 1
    {%- endif %}
    where seq.{{ link_hk }} is distinct from
          coalesce(seq.prev_link{% if is_incremental() %}, cur.{{ link_hk }}{% endif %})
    {%- if is_incremental() %}
      and not exists (
          select 1 from {{ this }} e
          join {{ link_rel }} l on l.{{ link_hk }} = e.{{ link_hk }}
          where l.{{ driving_key }} = seq.{{ driving_key }}
            and e.ingested_ts = seq.ingested_ts
      )
    {%- endif %}
)

select {{ link_hk }}, ingested_ts, event_ts, {{ dv_hash(['true']) }} as hash_diff, record_source, true as is_active
from chg
union all
select old_link, ingested_ts, event_ts, {{ dv_hash(['false']) }}, record_source, false
from chg
where old_link is not null
{%- endmacro %}


{# T-STS cho nguồn bản chụp đầy đủ (capture_mode: full_snapshot): khóa vắng khỏi một lô là DELETED, có lại là ACTIVE.
   Vắng dòng sts nghĩa là ACTIVE, nên chỉ ghi khi trạng thái đổi.
   - Lô trong cửa sổ và khóa có mặt lấy từ view hợp lệ ∪ __rejected: dòng bị loại (vd CYCLE_DETECTED) vẫn là có mặt,
     nên không bị xóa giả.
   - Chỉ xét khóa đã có phiên bản ở sat_model tính tới lô đó (khóa chỉ từng có dòng bị loại không vào vault). #}
{% macro dv_load_sts_snapshot(parent_hk, valid_model, rejected_model, sat_model) -%}
with rows_in_window as (
    select {{ parent_hk }}, ingested_ts, event_ts, record_source
    from {{ ref(valid_model) }}
    where {{ dv_window('ingested_ts') }}
    union all
    select {{ parent_hk }}, ingested_ts, event_ts, record_source
    from {{ ref(rejected_model) }}
    where {{ dv_window('ingested_ts') }}
),

batches as (
    select ingested_ts, min(event_ts) as event_ts, min(record_source) as record_source
    from rows_in_window
    group by ingested_ts
),

present as (
    select distinct {{ parent_hk }}, ingested_ts
    from rows_in_window
    where {{ parent_hk }} is not null
),

universe as (
    select {{ parent_hk }}, min(ingested_ts) as first_ts
    from {{ ref(sat_model) }}
    group by {{ parent_hk }}
),

grid as (
    select u.{{ parent_hk }}, b.ingested_ts, b.event_ts, b.record_source,
           case when p.{{ parent_hk }} is null then 'DELETED' else 'ACTIVE' end as status
    from universe u
    join batches b on b.ingested_ts >= u.first_ts
    left join present p on p.{{ parent_hk }} = u.{{ parent_hk }} and p.ingested_ts = b.ingested_ts
),

seq as (
    select g.*,
           lag(g.status) over (partition by g.{{ parent_hk }} order by g.ingested_ts) as prev_status,
           row_number() over (partition by g.{{ parent_hk }} order by g.ingested_ts) as rn
    from grid g
)

select seq.{{ parent_hk }}, seq.ingested_ts, seq.event_ts, seq.record_source, seq.status
from seq
{%- if is_incremental() %}
left join lateral (
    select t.status
    from {{ this }} t
    where t.{{ parent_hk }} = seq.{{ parent_hk }}
      and t.ingested_ts < seq.ingested_ts
    order by t.ingested_ts desc
    limit 1
) cur on seq.rn = 1
where seq.status <> coalesce(seq.prev_status, cur.status, 'ACTIVE')
  and not exists (
      select 1 from {{ this }} t
      where t.{{ parent_hk }} = seq.{{ parent_hk }} and t.ingested_ts = seq.ingested_ts
  )
{%- else %}
where seq.status <> coalesce(seq.prev_status, 'ACTIVE')
{%- endif %}
{%- endmacro %}
