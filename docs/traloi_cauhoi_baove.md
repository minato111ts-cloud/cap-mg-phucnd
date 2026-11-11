# Trả lời câu hỏi bảo vệ capstone v1.5 — CAP_MG

Số liệu trong tài liệu lấy từ database `cap_mg_phucnd` sau lần chạy đủ lịch 17/04 → 15/05/2026. Mọi ngày D dùng `cutoff(D) = 00:00 ngày D+1, giờ Việt Nam` (`asof_var_cutoff()` trong `finova-dbt/macros/asof/asof.sql`). Mỗi bảng kết quả ghi rõ as-of và cutoff; ảnh chụp đặt ở vị trí đánh dấu 📷.

---

## Câu 1. Phân công lùi hiệu lực (TH-LUIHIEULUC)

### 1.1. Ca thật

Lô `CAP-MG-0063` (`reaflnk_20260506.csv`) chuyển 4 tiểu khoản `9994000016..019` từ `BRK005` sang `BRK012` với hiệu lực từ 27/04, nhưng tới tối 06/05 hệ thống mới nhận. Lấy tiểu khoản `9994000016`:

| | autoid | Môi giới | FRDATE | TODATE | ingested_ts (giờ VN) |
|---|---|---|---|---|---|
| Phân công cũ, bản đầu | 16 | BRK005 | 19/06/2025 | 31/12/9999 | 17/04/2026 22:02 |
| Phân công cũ, bản đóng | 16 | BRK005 | 19/06/2025 | **26/04/2026** | 06/05/2026 22:02 |
| Phân công mới | **219** | **BRK012** | **27/04/2026** | 31/12/9999 | **06/05/2026 22:02** |

- Môi giới cũ: `BRK005`. Môi giới mới: `BRK012`.
- F = FRDATE = **27/04/2026**, K = ngày nhận = **06/05/2026**.
- Ngày giao dịch D thỏa F ≤ D < K: 27/04, 28/04, 29/04, 04/05, 05/05 (30/04 – 03/05 nghỉ theo `ref_calendar`). Chọn **D = 28/04/2026**.

Cùng một lô, nguồn làm hai việc: đóng phân công cũ lùi về 26/04 và mở phân công mới từ 27/04. Trong vault, đó là một phiên bản mới của satellite cho autoid 16 và một khóa phân công mới (autoid 219), cả hai cùng `ingested_ts` 06/05 22:02.

📷 **Ảnh 1.1** — lịch sử phiên bản trong raw vault (không phụ thuộc as-of; đọc toàn bộ vault).

```sql
select s.autoid, s.broker_id, s.afacctno, s.fr_date, s.to_date,
       to_char(s.ingested_ts at time zone 'Asia/Ho_Chi_Minh', 'YYYY-MM-DD HH24:MI') as ingested_vn
from atomic.sat_reaflnk__flex as s
where s.afacctno = '9994000016'
order by s.ingested_ts, s.autoid;
```

### 1.2. Ngày D = 28/04, bridge gán cho ai?

**BRK005.** Bridge đi qua ba bước, bước đầu tiên đã loại phân công mới:

**Bước 0: chỉ lấy điều đã biết tại cutoff(D).** View `asof__sat_reaflnk__flex` lấy, cho mỗi phân công, phiên bản có `ingested_ts` lớn nhất nhưng không vượt cutoff (`asof_latest` trong `macros/asof/asof.sql`). Cutoff(28/04) = 29/04 00:00, nên cả hai bản ghi ngày 06/05 bị loại. Hệ thống chỉ còn autoid 16 với TODATE 31/12/9999.

**Bước 1: giữ phân công đang hiệu lực ngày D** (`models/asof/asof__esat_reaflnk__flex.sql`):

```sql
where s.fr_date <= (select asof.as_of_date())
  and s.to_date >= (select asof.as_of_date())
```

19/06/2025 ≤ 28/04/2026 ≤ 31/12/9999, nên autoid 16 được giữ.

**Bước 2: chọn đúng một môi giới cho mỗi tiểu khoản** (`models/atomic/bv/bridge_account_broker.sql`, xếp hạng rồi lấy `rn = 1`). Chỉ còn một dòng nên BRK005 được chọn.

### 1.3. Sau ngày K, dựng lại ngày D: có đổi không?

**Không đổi, vẫn BRK005.** Cutoff được suy từ chính D, không lấy giờ chạy:

```sql
-- macros/asof/asof.sql
{% macro asof_var_cutoff() -%}
    (({{ asof_var_date() }} + 1)::timestamp at time zone 'Asia/Ho_Chi_Minh')
{%- endmacro %}
```

Dựng lại D = 28/04 ở bất kỳ thời điểm nào, kể cả full refresh sau 06/05, đều dùng cutoff 29/04 00:00 và đều loại hai bản ghi 06/05. Pre-hook `asof_day_delete()` xóa partition D rồi chèn lại, nên kết quả tất định. Đây là yêu cầu TC-CAP-MG-BACKDATE của đề: *"Sau khi có phân công lùi hiệu lực, dựng lại ngày cũ vẫn cho cùng kết quả với lần dựng đầu"* (test `test_tc_cap_mg_backdate`; probe `P-MG-BACKDATE` = `BRK005 (REAFLNK)`).

📷 **Ảnh 1.2** — kết quả Gold theo từng ngày.

```sql
select as_of_date,
       to_char(cutoff_ts at time zone 'Asia/Ho_Chi_Minh', 'YYYY-MM-DD HH24:MI') as cutoff_vn,
       broker_id, reaflnk_autoid, fr_date, to_date, care_basis
from mart.dim_account_care_daily
where account_id = '9994000016'
  and as_of_date in ('2026-04-27', '2026-04-28', '2026-05-05', '2026-05-06', '2026-05-15')
order by as_of_date;
```

| as_of_date | cutoff (VN) | broker_id | autoid | fr_date | to_date |
|---|---|---|---|---|---|
| 2026-04-27 | 2026-04-28 00:00 | BRK005 | 16 | 2025-06-19 | 9999-12-31 |
| 2026-04-28 | 2026-04-29 00:00 | **BRK005** | 16 | 2025-06-19 | 9999-12-31 |
| 2026-05-05 | 2026-05-06 00:00 | BRK005 | 16 | 2025-06-19 | 9999-12-31 |
| 2026-05-06 | 2026-05-07 00:00 | **BRK012** | 219 | 2026-04-27 | 9999-12-31 |
| 2026-05-15 | 2026-05-16 00:00 | BRK012 | 219 | 2026-04-27 | 9999-12-31 |

### 1.4. Hai cách trả lời "ngày D tiểu khoản thuộc ai"

| | Cách 1: điều đã biết tại ngày D | Cách 2: thực tế theo dữ liệu đã sửa |
|---|---|---|
| Lọc theo | `ingested_ts ≤ cutoff(D)` (trục thời gian hệ thống biết), rồi `FRDATE ≤ D ≤ TODATE` | `FRDATE ≤ D ≤ TODATE` (trục hiệu lực nghiệp vụ) trên bản đã biết mới nhất |
| Ngày 28/04 | BRK005 | BRK012 |
| Đọc ở Gold | `dim_account_care_daily` partition `as_of_date = 28/04` | `dim_account_care_daily` partition mới nhất, lọc `fr_date ≤ 28/04 ≤ to_date` |
| Phục vụ | Tái lập báo cáo đã phát hành, audit: "ngày 28/04 chúng tôi đã báo cáo gì" | Đánh giá, hoa hồng, KPI sau khi nguồn đã sửa: "ngày 28/04 thực sự ai chăm" |

Cách 2 đọc trực tiếp ở Gold:

```sql
select account_id, broker_id, reaflnk_autoid, fr_date, to_date
from mart.dim_account_care_daily
where as_of_date = '2026-05-15'                       -- cutoff 16/05 00:00
  and fr_date <= '2026-04-28' and to_date >= '2026-04-28'
  and account_id = '9994000016';
-- 9994000016 | BRK012 | 219 | 2026-04-27 | 9999-12-31
```

**Giới hạn của thiết kế hiện tại**, cần nêu rõ:

1. Cách 2 ở Gold chỉ đúng khi phân công đang thắng ở partition mới nhất cũng là phân công phủ ngày D. Ví dụ `9994000001` chuyển từ BRK003 sang BRK009 từ 11/05: partition 15/05 chỉ còn dòng BRK009 với `fr_date = 11/05`, câu lệnh trên không trả về tiểu khoản này cho ngày 28/04. Gold giữ phân công thắng theo ngày, không giữ lịch sử phân công.
2. Chỉ số của các ngày trước K **không được tính lại**. `met_broker_daily` có `business_date = as_of_date`, mỗi ngày nghiệp vụ chỉ một phiên bản. Ngày 28/04, 4 tiểu khoản `016..019` (NAV 7.450.532.000) vẫn nằm trong BOOKNAV của BRK005:

| as_of 28/04 (cutoff 29/04 00:00) | n_accounts | book_nav hiện tại | book_nav nếu tính lại theo dữ liệu đã sửa (tính tay) |
|---|---:|---:|---:|
| BRK005 | 11 | 16.381.059.000 | 8.930.527.000 (7 TK) |
| BRK012 | 7 | 12.374.932.000 | 19.825.464.000 (11 TK) |

Hướng mở rộng, theo đúng tinh thần DEC-ELT-RESTATE của đề (*"phiên bản mới cho đúng ngày nghiệp vụ đó; as-of trước ngày đính chính vẫn thấy số cũ"*): cho `met_broker_daily` grain `(business_date, as_of_date)`. Partition `(28/04, 28/04)` giữ BRK005 cho audit, TC-CAP-MG-BACKDATE vẫn xanh; partition `(28/04, 06/05)` tính lại cho BRK012. Ngày nghiệp vụ cần dựng lại được xác định bằng câu lệnh ở mục 1.5.

### 1.5. Nhận diện phân công lùi hiệu lực một cách tổng quát

Câu lệnh dưới đây không chứa mã tiểu khoản hay mã lô nào. Nó tìm mọi phiên bản phân công làm thay đổi kết quả của những ngày giao dịch **trước ngày hệ thống biết nó**:

- `NEW_BACKDATED`: phân công mới có FRDATE trước ngày nhận.
- `END_SHORTENED`: phiên bản mới rút TODATE về quá khứ (đóng dòng cũ lùi ngày).
- `START_EARLIER`: phiên bản mới dời FRDATE sớm hơn.

Lô nạp đầu (17/04) bị loại vì chứa dữ liệu lịch sử, không phải backdate. Chỉ giữ ca có ít nhất một ngày giao dịch bị ảnh hưởng.

```sql
with v as (
    select s.reaflnk_hk, s.autoid, s.broker_id, s.afacctno, s.fr_date, s.to_date, s.ingested_ts,
           (s.ingested_ts at time zone 'Asia/Ho_Chi_Minh')::date as known_date,
           row_number() over w as ver_no, lag(s.fr_date) over w as prev_fr, lag(s.to_date) over w as prev_to
    from atomic.sat_reaflnk__flex as s
    window w as (partition by s.reaflnk_hk order by s.ingested_ts)
),
classified as (
    select v.*,
        case
            when ver_no = 1 and fr_date < known_date                        then 'NEW_BACKDATED'
            when ver_no > 1 and to_date < prev_to and to_date < known_date  then 'END_SHORTENED'
            when ver_no > 1 and fr_date < prev_fr                           then 'START_EARLIER'
        end as kind
    from v
    where ingested_ts > (select min(ingested_ts) from atomic.sat_reaflnk__flex)
),
windowed as (
    select c.*,
        case kind when 'END_SHORTENED' then to_date + 1 else fr_date end      as affected_from,
        case kind when 'START_EARLIER' then least(prev_fr, known_date) - 1
                  else known_date - 1 end                                     as affected_to
    from classified as c
    where kind is not null
)
select w.afacctno, w.autoid, w.broker_id, w.kind, w.fr_date, w.to_date, w.prev_to,
       to_char(w.ingested_ts at time zone 'Asia/Ho_Chi_Minh', 'YYYY-MM-DD HH24:MI') as ingested_vn,
       d.n_days as affected_trading_days, d.first_d as first_affected_day, d.last_d as last_affected_day
from windowed as w
cross join lateral (
    select count(*) as n_days, min(c.calendar_date) as first_d, max(c.calendar_date) as last_d
    from staging.ref_calendar as c
    where c.is_trading_day = 1 and c.calendar_date between w.affected_from and w.affected_to
) as d
where d.n_days > 0
order by w.ingested_ts, w.afacctno, w.autoid;
```

📷 **Ảnh 1.5** — kết quả trên toàn bộ dữ liệu: đúng 8 dòng, không có dòng thừa.

| afacctno | autoid | broker | kind | fr_date | to_date | ingested (VN) | Số ngày GD bị ảnh hưởng | Từ | Đến |
|---|---|---|---|---|---|---|---:|---|---|
| 9994000016 | 16 | BRK005 | END_SHORTENED | 2025-06-19 | 2026-04-26 | 2026-05-06 22:02 | 5 | 2026-04-27 | 2026-05-05 |
| 9994000016 | 219 | BRK012 | NEW_BACKDATED | 2026-04-27 | 9999-12-31 | 2026-05-06 22:02 | 5 | 2026-04-27 | 2026-05-05 |
| 9994000017 | 17 / 220 | BRK005 / BRK012 | như trên | | | | 5 | 2026-04-27 | 2026-05-05 |
| 9994000018 | 18 / 221 | BRK005 / BRK012 | như trên | | | | 5 | 2026-04-27 | 2026-05-05 |
| 9994000019 | 19 / 222 | BRK005 / BRK012 | như trên | | | | 5 | 2026-04-27 | 2026-05-05 |

Các thay đổi khác không bị báo nhầm: lô 04/05 đóng phân công BRK017 ở 03/05 không ảnh hưởng ngày giao dịch nào; lô 08/05 đặt TODATE 10/05 ở tương lai; lô 11/05 đóng autoid 216..218 ở 08/05 cũng không có ngày giao dịch nào giữa 08/05 và 11/05.

Khi vận hành, câu lệnh này dùng được làm cờ DQ mới trong `dq_mg_daily` (ví dụ `BACKDATED_ASSIGNMENT`), và cột `first_affected_day..last_affected_day` cho biết business_date nào cần tính lại theo hướng ở mục 1.4.

---

## Câu 2. Một mã môi giới, hai người (DQ-KHOA-TAISUDUNG)

**Trả lời ngắn.**

| Câu hỏi | Trả lời |
|---|---|
| Có `broker_id` nào được hai người dùng ở hai giai đoạn không? | **Có: `BRK017`.** Ngô Đức Châu (JOINDATE 14/05/2025, nghỉ 30/04/2026), rồi từ lô 11/05/2026 mã cấp lại cho Lý Minh Sơn (JOINDATE 11/05/2026). Một khóa hub, ba phiên bản hồ sơ. |
| Ở `met_broker_daily` ngày D, cái gì phân biệt đúng người giữ mã? | **`broker_key = BROKERID:JOINDATE`** của phiên bản hồ sơ hiệu lực tại cutoff(D), cùng khoảng làm việc `[join_date, leave_date]` của người đó, dùng để lọc mọi dữ liệu chỉ mang mã. |
| Người mới có kế thừa `kpi_target_calls` của người cũ không? Chặn ở đâu? | **Không.** Chặn ở Gold, CTE `kpi` của `met_broker_daily`: chỉ tiêu chỉ áp khi `approved_date` nằm trong khoảng làm việc của người đang mang mã. Dữ liệu đề không có chỉ tiêu nào của BRK017, nên chốt chặn được chứng minh bằng unit test. |

### 2.1. Ca thật: BRK017

`broker_hk = dv_hash('FLEX', BROKERID)` nên mọi người mang `BRK017` có chung một khóa hub (`3614e490…f17a`; `hub_broker` chỉ có 1 dòng cho BRK017). Hai người được tách ở satellite hồ sơ `sat_broker_profile__flex`, gồm 3 phiên bản:

📷 **Ảnh 2.1**

```sql
select to_char(ingested_ts at time zone 'Asia/Ho_Chi_Minh', 'YYYY-MM-DD HH24:MI') as ingested_vn,
       broker_id, broker_key, status, join_date, leave_date, encode(broker_hk, 'hex') as broker_hk
from atomic.sat_broker_profile__flex
where broker_id = 'BRK017'
order by ingested_ts;
```

| ingested (VN) | broker_key | STATUS | JOINDATE | LEAVEDATE | Người |
|---|---|---|---|---|---|
| 2026-04-17 22:01 | BRK017:2025-05-14 | A | 2025-05-14 | | Ngô Đức Châu |
| 2026-05-04 22:01 | BRK017:2025-05-14 | C | 2025-05-14 | 2026-04-30 | Ngô Đức Châu nghỉ việc |
| 2026-05-11 22:01 | BRK017:2026-05-11 | A | 2026-05-11 | | Lý Minh Sơn |

- **Giai đoạn 1:** Ngô Đức Châu chăm 13 tiểu khoản và nghỉ ngày 30/04. Từ lô 04/05, 13 tiểu khoản chuyển sang BRK018 (autoid 203..215).
- **Giai đoạn 2:** từ lô `CAP-MG-0079` (11/05), mã được cấp lại cho Lý Minh Sơn. Tới 15/05, người mới chưa được giao tiểu khoản nào và chưa có tương tác nào.
- **Tương tác:** cả 16 tương tác của BRK017 trong `nhl_broker_event` đều nằm trong 20/04 – 29/04, tức đều là của người cũ.
- **Cờ DQ:** `dq_mg_daily` ngày 11/05 ghi `KEY_REUSED` (DQ-KHOA-TAISUDUNG) cho lô `CAP-MG-0079`, khóa mẫu `BRK017`.

Lý do sinh phiên bản mới thay vì ghi đè: JOINDATE nằm trong `hash_diff` của satellite, nên khi mã được cấp lại cho người khác thì hash đổi (DEC-CAP-MG-BROKERKEY, phương án A).

### 2.2. Ở met_broker_daily ngày D, cái gì phân biệt người?

Khóa hub **không** phân biệt được, vì hai người có chung `broker_hk`. Người được phân biệt nhờ ba thứ, cả ba đều suy từ phiên bản hồ sơ hiệu lực tại cutoff(D).

**1. `broker_key = BROKERID:JOINDATE`.** Chuỗi suy ra là `pit_broker_daily` (con trỏ tới phiên bản hồ sơ tại cutoff(D)) → `dim_broker_org_daily` → `met_broker_daily`. Grain của `met_broker_daily` là `(business_date, broker_key)`, nên mỗi người có một dòng riêng. Vì `broker_key` lấy theo cutoff(D), dựng lại ngày 08/05 vào bất kỳ lúc nào vẫn ra người cũ.

📷 **Ảnh 2.2a**

```sql
select as_of_date, broker_key, join_date, leave_date, broker_status, work_status
from mart.dim_broker_org_daily
where broker_id = 'BRK017'
  and as_of_date in ('2026-04-29', '2026-05-04', '2026-05-08', '2026-05-11', '2026-05-15')
order by as_of_date;
```

| as_of | broker_key | join_date | leave_date | STATUS | work_status |
|---|---|---|---|---|---|
| 2026-04-29 | BRK017:2025-05-14 | 2025-05-14 | | A | ACTIVE |
| 2026-05-04 | BRK017:2025-05-14 | 2025-05-14 | 2026-04-30 | C | LEFT |
| 2026-05-08 | BRK017:2025-05-14 | 2025-05-14 | 2026-04-30 | C | LEFT |
| 2026-05-11 | **BRK017:2026-05-11** | **2026-05-11** | | A | ACTIVE |
| 2026-05-15 | BRK017:2026-05-11 | 2026-05-11 | | A | ACTIVE |

**2. Khoảng làm việc `[join_date, leave_date]`.** Tương tác và chỉ tiêu chỉ mang mã, không mang JOINDATE. Gold chỉ tính cho người đang mang mã những bản ghi có ngày nằm trong khoảng làm việc của người đó. Điều kiện này nằm ở một chỗ, macro `gold_in_tenure` (nguyên văn ở mục 2.3, ①). Với tương tác, `finova-dbt/models/gold/met_broker_daily.sql` dòng 41–48:

```sql
 41 | event as (
 42 |     select b.broker_key, b.broker_hk, e.event_id, e.account_hk, e.event_type, e.event_date
 43 |     from broker as b
 44 |     inner join {{ ref('asof__nhl_broker_event') }} as e on e.broker_hk = b.broker_hk
 45 |     where e.event_date <= {{ asof_var_date() }}
 46 |       and e.event_date >= least({{ asof_var_date() }} - 29, date_trunc('quarter', {{ asof_var_date() }})::date)
 47 |       and {{ gold_in_tenure('e.event_date', 'b') }}          -- ◀ ngày sự kiện trong khoảng làm việc
 48 | ),
```

**3. Phân công.** `n_accounts` và `book_nav` đọc tiểu khoản qua `bridge_account_broker`. Các phân công của người cũ đã đóng ở 03/05, và người mới chưa được giao tiểu khoản nào, nên người mới có 0 tiểu khoản.

📷 **Ảnh 2.2b**

```sql
select as_of_date,
       to_char(cutoff_ts at time zone 'Asia/Ho_Chi_Minh', 'YYYY-MM-DD HH24:MI') as cutoff_vn,
       broker_key, n_accounts, book_nav, interactions_30d, cover30_num, cover30_den,
       kpi_target_calls, calls_qtd
from mart.met_broker_daily
where broker_id = 'BRK017'
  and as_of_date in ('2026-04-29', '2026-05-04', '2026-05-08', '2026-05-11', '2026-05-12', '2026-05-15')
order by as_of_date;
```

| as_of | cutoff (VN) | broker_key | n_accounts | book_nav | interactions_30d | kpi_target_calls | calls_qtd |
|---|---|---|---:|---:|---:|---|---:|
| 2026-04-29 | 2026-04-30 00:00 | BRK017:2025-05-14 | 13 | 22.129.625.000 | 16 | NULL | 8 |
| 2026-05-04 | 2026-05-05 00:00 | BRK017:2025-05-14 | 0 | 0 | 16 | NULL | 8 |
| 2026-05-08 | 2026-05-09 00:00 | BRK017:2025-05-14 | 0 | 0 | 16 | NULL | 8 |
| 2026-05-11 | 2026-05-12 00:00 | **BRK017:2026-05-11** | 0 | 0 | **0** | NULL | 0 |
| 2026-05-12 | 2026-05-13 00:00 | BRK017:2026-05-11 | 0 | 0 | **0** | NULL | 0 |
| 2026-05-15 | 2026-05-16 00:00 | BRK017:2026-05-11 | 0 | 0 | **0** | NULL | 0 |

Từ 11/05, cửa sổ 30 ngày vẫn phủ 20/04 – 29/04. Nhưng 16 tương tác của người cũ nằm trước `join_date = 11/05` của người mới, nên bị loại. Nếu bỏ điều kiện khoảng làm việc, người mới nhận nhầm **16** tương tác và test `test_dec_brokerkey_new_holder_has_no_old_interactions` (`tests/gold/test_care_metrics.py`) đỏ.

### 2.3. Chỉ tiêu kpi_target_calls: người mới có kế thừa không, chặn ở đâu?

**Không kế thừa. Chặn ở Gold, CTE `kpi` của `met_broker_daily`.**

**Vì sao cần chặn.** Đúng như đề nói, chỉ tiêu gắn theo `broker_id`. File `manual_kpi` chỉ có mã, người duyệt và ngày duyệt, không có JOINDATE; vào vault nó nối theo `broker_hk = dv_hash('FLEX', broker_id)`, chung cho cả hai người. Nếu nối thẳng theo `broker_hk`, chỉ tiêu duyệt cho Ngô Đức Châu sẽ hiện ở dòng của Lý Minh Sơn.

**Trên dữ liệu đề.** File `kpi_targets_2026Q2_v1/v2` không có dòng nào của BRK017, nên `kpi_target_calls` NULL cho cả hai người ở mọi ngày (Ảnh 2.2b). Thiết kế không dựa vào sự may mắn này.

**Cách chặn.** Gold gắn chỉ tiêu vào người bằng **ngày duyệt**: chỉ áp khi `approved_date` nằm trong `[join_date, leave_date]` của người đang mang mã tại D. Đây cùng là macro lọc tương tác ở mục 2.2.

#### Code chặn

Ba chỗ, theo thứ tự chạy: quy tắc (macro), chặn (`met_broker_daily`), ghi cờ (`dq_mg_daily`). Số dòng theo commit `7f4c86c` trên `main`. Ký hiệu `◀` là chú thích thêm trong tài liệu, không có trong file.

**① Quy tắc khoảng làm việc**: `finova-dbt/macros/gold/gold.sql`, dòng 47–52

```sql
 47 | {# Ngày nằm trong khoảng làm việc [join_date, leave_date] của người mang mã ở alias (DEC-CAP-MG-BROKERKEY): mã cấp
 48 |    lại không kéo tương tác, chỉ tiêu của người cũ sang người mới. join_date, leave_date NULL thì không chặn đầu đó. #}
 49 | {% macro gold_in_tenure(date_expr, alias) -%}
 50 |     ({{ alias }}.join_date is null or {{ date_expr }} >= {{ alias }}.join_date)     -- ◀ không trước ngày vào
 51 |     and ({{ alias }}.leave_date is null or {{ date_expr }} <= {{ alias }}.leave_date) -- ◀ không sau ngày nghỉ
 52 | {%- endmacro %}
```

**② Chặn chỉ tiêu**: `finova-dbt/models/gold/met_broker_daily.sql`

Người đang mang mã tại D, kèm `join_date` và `leave_date` của người đó, lấy từ `dim_broker_org_daily` (dòng 16–20):

```sql
 16 | with broker as (
 17 |     select broker_hk, broker_key, broker_id, join_date, leave_date
 18 |     from {{ ref('dim_broker_org_daily') }}
 19 |     where as_of_date = {{ asof_var_date() }}
 20 | ),
```

CTE `kpi` (dòng 104–126). Dòng 114 gắn chỉ tiêu vào **người**, dòng 117 là **điểm chặn**:

```sql
104 | -- chỉ tiêu: phiên bản trỏ bởi PIT tại cutoff(D) (TH-NHAPTAY), chỉ áp khi ngày duyệt nằm trong khoảng làm việc của
105 | -- người mang mã; duyệt ngoài khoảng (vd cho người cũ của mã cấp lại) thì không có chỉ tiêu, cờ KPI_NOT_FOR_HOLDER ở
106 | -- dq_mg_daily. Lô của phiên bản tra ở sổ nạp
107 | kpi as (
108 |     select
109 |         b.broker_key,                                                  -- ◀ khóa người, không phải khóa mã
110 |         k.target_calls,
111 |         k.ingested_ts as kpi_ingested_ts,
112 |         bl.batch_id as kpi_batch_id
113 |     from {{ ref('pit_broker_daily') }} as p
114 |     inner join broker as b on b.broker_hk = p.broker_hk                -- ◀ người đang mang mã tại D
115 |     inner join {{ ref('asof__sat_broker_kpi__manual') }} as k
116 |         on k.broker_hk = p.broker_hk and k.ingested_ts = p.sat_broker_kpi_ingested_ts
117 |        and {{ gold_in_tenure('k.approved_date', 'b') }}               -- ◀ CHẶN: ngày duyệt ngoài khoảng làm việc thì loại
118 |     left join (
119 |         select distinct on (source_table, ingested_ts) source_table, ingested_ts, batch_id
120 |         from {{ source('ctrl', 'batch_log') }}
121 |         where status = 'LOADED'
122 |         order by source_table, ingested_ts, log_id desc
123 |     ) as bl
124 |         on bl.source_table = split_part(k.record_source, '.', 2) and bl.ingested_ts = k.ingested_ts
125 |     where p.as_of_date = {{ asof_var_date() }}
126 | ),
```

Dòng 117 sau khi dbt compile (câu PostgreSQL thực chạy):

```sql
       and (b.join_date is null or k.approved_date >= b.join_date)
       and (b.leave_date is null or k.approved_date <= b.leave_date)
```

CTE `final`, dòng 143 và 151: chỉ tiêu nối theo `broker_key`. Dòng nào bị loại ở dòng 117 thì ở đây ra NULL:

```sql
143 |         k.target_calls as kpi_target_calls,
...
147 |     from broker as b
...
151 |     left join kpi as k on k.broker_key = b.broker_key                  -- ◀ nối theo người; bị chặn → NULL
```

Trước khi sửa, dòng 151 là `left join kpi as k on k.broker_hk = b.broker_hk` và CTE `kpi` không có dòng 114, 117. Vì `broker_hk` chung cho hai người, chỉ tiêu của người cũ đi thẳng sang người mới.

**③ Ghi cờ cho nghiệp vụ**: `finova-dbt/models/gold/dq_mg_daily.sql`

Dòng 54–66 dùng cùng macro nhưng lấy **phủ định** (dòng 65), tức đúng tập chỉ tiêu bị chặn ở ②:

```sql
 54 | kpi_not_for_holder as (
 55 |     select
 56 |         b.broker_id,
 57 |         case when k.ingested_ts >= b.ingested_ts then k.record_source else b.record_source end as record_source,
 58 |         greatest(k.ingested_ts, b.ingested_ts) as ingested_ts          -- ◀ lô gây ra lệch: con trỏ mới hơn
 59 |     from {{ ref('pit_broker_daily') }} as p
 60 |     inner join {{ ref('asof__sat_broker_profile__flex') }} as b
 61 |         on b.broker_hk = p.broker_hk and b.ingested_ts = p.sat_broker_profile_ingested_ts
 62 |     inner join {{ ref('asof__sat_broker_kpi__manual') }} as k
 63 |         on k.broker_hk = p.broker_hk and k.ingested_ts = p.sat_broker_kpi_ingested_ts
 64 |     where p.as_of_date = {{ asof_var_date() }}
 65 |       and not ({{ gold_in_tenure('k.approved_date', 'b') }})            -- ◀ đúng phần bị chặn ở ②
 66 | ),
```

Dòng 118–123 đưa từng ca vào báo cáo DQ, gắn vào lô của ngày phát sinh:

```sql
118 |     -- DQ-KHOA-TAISUDUNG: chỉ tiêu không áp cho người đang mang mã (duyệt ngoài khoảng làm việc)
119 |     select l.source_table, l.batch_id, 'KPI_NOT_FOR_HOLDER', n.broker_id, false
120 |     from kpi_not_for_holder as n
121 |     inner join last_log as l
122 |         on l.status = 'LOADED' and l.source_table = split_part(n.record_source, '.', 2)
123 |        and l.ingested_ts = n.ingested_ts
```

#### Đọc code theo một ca giả định

Giả sử file chỉ tiêu có dòng `BRK017`, `approved_date = 21/04/2026` (duyệt cho Ngô Đức Châu). Dựng ngày D = 12/05:

| Bước | Dòng code | Kết quả |
|---|---|---|
| PIT trỏ tới phiên bản chỉ tiêu của `broker_hk` BRK017 | `met_broker_daily.sql` 113, 116 | Tìm thấy chỉ tiêu (chung khóa hub) |
| Nối người đang mang mã tại 12/05 | 114 | `BRK017:2026-05-11`, `join_date = 11/05/2026` |
| Kiểm ngày duyệt | 117 | 21/04 < 11/05 → **loại**, CTE `kpi` không có dòng cho người mới |
| Nối vào chỉ số | 151 | Không khớp → `kpi_target_calls = NULL` |
| Ghi cờ | `dq_mg_daily.sql` 65, 119 | `KPI_NOT_FOR_HOLDER` gắn vào lô hồ sơ `CAP-MG-0079` (cấp lại mã), khóa mẫu `BRK017` |

Ngày 29/04 thì người mang mã là `BRK017:2025-05-14`, có `join_date = 14/05/2025` và chưa nghỉ. Ngày duyệt 21/04/2026 nằm trong khoảng, nên Ngô Đức Châu nhận chỉ tiêu bình thường.

- Chỉ tiêu duyệt cho người cũ, tức trước `join_date = 11/05` của người mới: người mới có `kpi_target_calls` NULL.
- Chỉ tiêu duyệt sau khi người cũ đã nghỉ (sau `leave_date`) cũng không áp cho người cũ.
- So `approved_date` chứ không so `ingested_ts`: file chỉ tiêu là bản chụp đầy đủ, nên một bản nạp sau 11/05 vẫn có thể chép nguyên dòng duyệt cho người cũ. Khi đó `ingested_ts` mới nhưng ngày duyệt vẫn cũ.

**Vì sao chặn ở Gold, không chặn ở tầng khác.**

| Tầng | Vì sao không chặn ở đây |
|---|---|
| Staging | File chỉ tiêu không có JOINDATE. Muốn biết người phải tra sang `flex_broker`, trái quy tắc chỉ tra khóa trong cùng nguồn (Q19). |
| Raw vault | Giữ đúng điều nguồn gửi. Hub khóa theo mã (DEC-CAP-MG-BROKERKEY phương án A), nên không có khái niệm người. |
| Business Vault (`pit_broker_daily`) | PIT chỉ chứa con trỏ tới phiên bản, không thuộc tính, không logic (Q18). |
| **Gold** | Là nơi duy nhất có cả phiên bản hồ sơ tại cutoff(D) (biết `join_date`, `leave_date`) lẫn phiên bản chỉ tiêu PIT trỏ tới. Cũng là nơi đã lọc tương tác, nên một quy tắc nằm ở một chỗ. |

**Không mất dấu.** Chỉ tiêu bị chặn không biến mất trong im lặng. `dq_mg_daily` ghi cờ `KPI_NOT_FOR_HOLDER` (DQ-KHOA-TAISUDUNG, xử lý QUYETDINH) để nghiệp vụ duyệt lại. Cờ gắn vào lô gây ra lệch: lô hồ sơ cấp lại mã, hoặc lô chỉ tiêu nếu file đến sau. Trên dữ liệu đề không có cờ nào; ngày 11/05 chỉ có `KEY_REUSED`.

📷 **Ảnh 2.3a**

```sql
select as_of_date, batch_id, source_table, reason_code, defect_code, key_sample
from mart.dq_mg_daily
where reason_code in ('KEY_REUSED', 'KPI_NOT_FOR_HOLDER')
order by as_of_date;
-- 2026-05-11 | CAP-MG-0079 | flex_broker | KEY_REUSED | DQ-KHOA-TAISUDUNG | BRK017
```

**Bằng chứng chốt chặn chạy đúng.** Gói đề không có ca này, nên chốt chặn được thử bằng unit test trên dữ liệu giả (`models/gold/_gold__unit_tests.yml`). Phép thử âm là tạm bỏ điều kiện `gold_in_tenure` ở CTE `kpi`.

| Môi giới giả, D = 12/05 | join / leave | Ngày duyệt | `kpi_target_calls` | Bỏ chốt chặn |
|---|---|---|---:|---:|
| BRK017 người mới | 11/05/2026 / — | 21/04/2026 | **NULL** | 300 (của người cũ) |
| BRK040 đã nghỉ | 02/01/2024 / 30/04/2026 | 06/05/2026 | **NULL** | 200 |
| BRK003 (đối chứng) | 02/01/2024 / — | 21/04/2026 | 440 | 440 |

📷 **Ảnh 2.3b**: kết quả unit test, rồi kết quả phép thử âm.

```powershell
uv run --env-file .env dbt test --select "ut_met_kpi_not_for_new_holder ut_dq_kpi_not_for_holder_on_reuse_batch" @dbt `
    --vars '{lo_ts: "-infinity", hi_ts: "2026-05-15T23:59:59+07:00"}'
# PASS met_broker_daily::ut_met_kpi_not_for_new_holder
# PASS dq_mg_daily::ut_dq_kpi_not_for_holder_on_reuse_batch
```

```text
-- phép thử âm: bỏ gold_in_tenure ở CTE kpi
FAIL 1 met_broker_daily::ut_met_kpi_not_for_new_holder
actual differs from expected:
  ,BRK003:2024-01-02,440       ,CAP-MG-0103
→ ,BRK017:2026-05-11,NULL→300  ,NULL→CAP-MG-0103
→ ,BRK040:2024-01-02,NULL→200  ,NULL→CAP-MG-0104
```

- `ut_dq_kpi_not_for_holder_on_reuse_batch` kiểm cờ `KPI_NOT_FOR_HOLDER` gắn đúng lô hồ sơ cấp lại mã.
- `test_gold_kpi_holder.sql` chạy trên dữ liệu thật ở mỗi lần dựng Gold để chặn hồi quy.
- Thêm chốt chặn không đổi số liệu nào trên gói đề: md5 mọi bảng `mart` như cũ (`evidence/row_counts_compare.csv`).

**Đánh đổi.** Chỉ tiêu duyệt trước cho người sắp nhận mã (duyệt trước JOINDATE) cũng bị chặn. Trường hợp này chờ nghiệp vụ xác nhận qua cờ DQ, không tự gán.

---

## Câu 3. Phân công chồng ngày và độ phủ COVER30

### 3.1. Ca thật: 9994000026

Lô 04/05 giao `9994000026` cho BRK021 (autoid 216, FRDATE 04/05/2026) nhưng không đóng phân công cũ của BRK010 (autoid 26, FRDATE 15/04/2025, TODATE 31/12/9999). Từ 04/05, cả hai đều thỏa `FRDATE ≤ D ≤ TODATE`, nên sau bước lọc hiệu lực tiểu khoản có hai môi giới (DQ-CHONGLAN). Ngày 05/05 có 3 tiểu khoản như vậy: 026, 027, 028.

| autoid | Môi giới | FRDATE | TODATE | ingested (VN) |
|---|---|---|---|---|
| 26 | BRK010 | 2025-04-15 | 9999-12-31 | 2026-04-17 22:02 |
| 216 | BRK021 | 2026-05-04 | 9999-12-31 | 2026-05-04 22:02 |

### 3.2. Dòng nào thắng?

Bridge xếp hạng theo ba tiêu chí. Tiêu chí sau chỉ dùng khi tiêu chí trước hòa (`bridge_account_broker.sql`):

```sql
row_number() over (
    partition by a.account_hk
    order by a.fr_date desc,                 -- 1. FRDATE mới hơn thắng
             a.ingested_ts desc,             -- 2. biết sau thắng
             case when a.autoid ~ '^[0-9]+$' then a.autoid::numeric end desc nulls last,
             a.autoid desc                   -- 3. AUTOID lớn hơn thắng (so số, không so chuỗi)
) as rn
...
where r.rn = 1
```

- Tiêu chí 1 đã phân định: 04/05/2026 mới hơn 15/04/2025, **autoid 216, BRK021 thắng**. Lý do nghiệp vụ: phân công mới sinh ra để thay phân công cũ, dòng cũ còn sót là do nguồn quên đóng.
- Tiêu chí 2 dùng khi hai phân công cùng FRDATE: bản biết sau là thông tin mới nhất.
- Tiêu chí 3 dùng khi vẫn hòa: AUTOID lớn hơn là dòng tạo sau ở nguồn. AUTOID so như số để `'216' > '26'` đúng thứ tự.

📷 **Ảnh 3.1**

```sql
select as_of_date, account_id, broker_id, reaflnk_autoid, fr_date, to_date, is_overlap, care_basis
from mart.dim_account_care_daily
where account_id = '9994000026' and as_of_date between '2026-05-04' and '2026-05-12'
order by as_of_date;
```

| as_of | broker_id | autoid | is_overlap | care_basis |
|---|---|---|---|---|
| 2026-05-04 … 2026-05-08 | BRK021 | 216 | true | REAFLNK+DEC-CAP-MG-OVERLAP |
| 2026-05-11, 2026-05-12 | BRK010 | 26 | false | REAFLNK |

Từ 11/05, lô 11/05 đóng autoid 216 ở 08/05 nhưng autoid 26 của BRK010 vẫn chưa bao giờ được đóng, nên tiểu khoản quay về BRK010. Kết quả này đúng theo dữ liệu nguồn, nhưng đáng đưa cho nghiệp vụ xác nhận.

### 3.3. book_nav vào ai, môi giới không được chọn có vào n_accounts không?

Bridge giữ đúng một dòng cho mỗi tiểu khoản, và mọi chỉ số Gold đọc tiểu khoản qua bridge (`care` trong `met_broker_daily.sql` lấy từ `dim_account_care_daily`, vốn lấy từ bridge). Vì vậy:

- `book_nav` của `9994000026` (2.781.711.000 ngày 05/05) chỉ cộng vào **BRK021**.
- BRK010 **không** tính tiểu khoản này vào `n_accounts`, dù phân công của BRK010 vẫn còn hiệu lực.
- Không mất dấu vết: cờ `is_overlap = true` ở `dim_account_care_daily` và mã DQ-CHONGLAN (`ASSIGNMENT_OVERLAP`) ở `dq_mg_daily`.

📷 **Ảnh 3.2** (as-of 05/05, cutoff 06/05 00:00)

```sql
select as_of_date, broker_key, n_accounts, book_nav, interactions_30d, cover30_num, cover30_den, round(cover30, 4) as cover30
from mart.met_broker_daily
where broker_id in ('BRK010', 'BRK021') and as_of_date = '2026-05-05'
order by broker_key;
```

| broker_key | n_accounts | book_nav | cover30_num / den |
|---|---:|---:|---|
| BRK010:2024-07-05 | 9 | 16.244.048.000 | 8 / 9 |
| BRK021:2024-06-30 | 10 (7 riêng + 3 chồng lấn) | 15.114.758.000 | 7 / 10 |

Nếu tính cho cả hai, tổng công ty thừa 7.770.720.000 (NAV của 3 tiểu khoản chồng lấn bị đếm hai lần), vi phạm C-SA-ONEBROKER.

### 3.4. COVER30: một tiểu khoản có 5 tương tác trong 30 ngày

COVER30 đo độ phủ theo tiểu khoản: trong các tiểu khoản môi giới đang chăm tại D, bao nhiêu tiểu khoản được chính môi giới đó liên hệ ít nhất một lần trong 30 ngày lịch kết thúc tại D.

```sql
covered as (
    select distinct c.broker_key, c.account_hk          -- mỗi (môi giới, tiểu khoản) đếm 1 lần
    from care as c
    inner join event as e
        on e.broker_key = c.broker_key                   -- tương tác của chính người đang chăm
       and e.account_hk = c.account_hk
       and e.event_date >= {{ asof_var_date() }} - 29    -- trong 30 ngày
    where exists (
        select 1 from assignment as a
        where a.broker_hk = c.broker_hk and a.account_hk = e.account_hk
          and e.event_date between a.fr_date and a.to_date   -- vào ngày đang được giao
    )
),
...
count(distinct event_id) filter (where event_date >= {{ asof_var_date() }} - 29) as interactions_30d
```

**Ca thật: `9994000126`, môi giới BRK006, as-of 15/05 (cutoff 16/05 00:00).** Trong 30 ngày có 5 tương tác của BRK006 (24/04 NOTE, 27/04 CALL, 28/04 CALL, 05/05 MSG, 05/05 NOTE) và 1 tương tác của BRK009 (13/05 NOTE).

| Chỉ số | Đóng góp từ tiểu khoản này | Lý do |
|---|---|---|
| `cover30_num` của BRK006 | **+1** | `select distinct broker_key, account_hk`: 5 tương tác vẫn là 1 tiểu khoản |
| `cover30_den` của BRK006 | +1 | tiểu khoản đang được BRK006 chăm |
| `interactions_30d` của BRK006 | **+5** | `count(distinct event_id)`: đếm từng tương tác |
| `interactions_30d` của BRK009 | +1 | tương tác thuộc người thực hiện |
| `cover30_num` của BRK009 | 0 | BRK009 không chăm tiểu khoản này (DQ-QUYEN), không tính độ phủ |

### 3.5. Đổi môi giới giữa kỳ 30 ngày: tương tác cũ tính cho ai?

**Trả lời ngắn.** Hai chỉ số hỏi hai câu khác nhau, nên một tương tác được gắn theo hai cách khác nhau:

| Chỉ số | Câu hỏi nghiệp vụ | Tương tác tính cho ai |
|---|---|---|
| `interactions_30d` | Môi giới này đã làm bao nhiêu việc? | **Người thực hiện**, bất kể hôm nay ai đang chăm tiểu khoản |
| `cover30_num` / `cover30_den` | Người đang chịu trách nhiệm có chăm khách của mình không? | Tiểu khoản thuộc **người đang chăm tại D**. Tiểu khoản chỉ "được phủ" khi có tương tác của **chính người đó, trong thời gian được giao** |

Hệ quả: người cũ giữ nguyên số tương tác đã làm nhưng tiểu khoản rời khỏi cả tử lẫn mẫu COVER30 của họ. Người mới nhận tiểu khoản vào mẫu ngay, nhưng phải tự liên hệ khách thì mới vào tử. Độ phủ không được kế thừa.

#### Ca thật: `9994000010`

| Thời điểm | Diễn biến |
|---|---|
| 27/04/2025 | Autoid 10 giao tiểu khoản cho BRK003, `TODATE = 31/12/9999` |
| 22/04 → 06/05/2026 | BRK003 có 6 tương tác: 22/04 (NOTE, CALL), 27/04 (CALL, CALL), 05/05 (MEET), 06/05 (MSG) |
| Lô 08/05, 22:02 | Nguồn đóng autoid 10 ở `TODATE = 10/05` và mở autoid 232 giao cho BRK009 từ `11/05` |
| 13/05 → 15/05 | BRK009 có 3 tương tác: 13/05 (MSG), 14/05 (NOTE), 15/05 (MSG) |

Từ 11/05, 6 tương tác của BRK003 vẫn nằm trong cửa sổ 30 ngày. Câu hỏi là chúng có giúp BRK009 đạt độ phủ không.

#### Theo dõi từng ngày

📷 **Ảnh 3.3**: đóng góp của riêng tiểu khoản `9994000010` vào chỉ số của người đang chăm

```sql
select d.as_of_date,
       d.broker_id                                                   as nguoi_cham,
       count(e.event_id) filter (where h.broker_id = 'BRK003')       as tt_brk003,
       count(e.event_id) filter (where h.broker_id = 'BRK009')       as tt_brk009,
       case when count(e.event_id) filter (where e.broker_hk = d.broker_hk
                                             and e.event_date >= d.fr_date) > 0
            then 1 else 0 end                                        as vao_tu_so
from mart.dim_account_care_daily as d
left join atomic.nhl_broker_event as e
       on e.account_hk = d.account_hk
      and e.event_date between d.as_of_date - 29 and d.as_of_date
left join atomic.hub_broker as h on h.broker_hk = e.broker_hk
where d.account_id = '9994000010'
  and d.as_of_date between '2026-05-08' and '2026-05-15'
group by d.as_of_date, d.broker_id
order by d.as_of_date;
```

| as-of | Người chăm | Tương tác 30 ngày của BRK003 | Tương tác 30 ngày của BRK009 | Vào tử COVER30 của người chăm | Giải thích |
|---|---|---:|---:|---:|---|
| 08/05 | BRK003 | 6 | 0 | 1 | BRK003 đang chăm và đã liên hệ |
| 11/05 | BRK009 | 6 | 0 | **0** | Đã đổi người. 6 tương tác cũ vẫn trong cửa sổ nhưng là của BRK003, không tính cho BRK009 |
| 12/05 | BRK009 | 6 | 0 | **0** | BRK009 vẫn chưa liên hệ: tiểu khoản nằm trong mẫu nhưng không vào tử |
| 13/05 | BRK009 | 6 | 1 | **1** | BRK009 liên hệ lần đầu (MSG), tiểu khoản được phủ |
| 14/05 | BRK009 | 6 | 2 | 1 | Thêm tương tác chỉ tăng `interactions_30d`, tử số vẫn 1 (xem 3.4) |
| 15/05 | BRK009 | 6 | 3 | 1 | |

Ngày 11/05 và 12/05 là bằng chứng chính: nếu cho kế thừa, tiểu khoản đã vào tử của BRK009 từ 11/05 nhờ cuộc gọi ngày 05/05, 06/05 của BRK003.

Câu SQL trên dùng cho ảnh minh họa nên không lọc `ingested_ts` theo cutoff. Với tiểu khoản này kết quả không đổi, vì mỗi sự kiện đều được nạp lúc 23:30 cùng ngày, trước cutoff 00:00 hôm sau. Trong Gold, điều kiện tương ứng nằm ở đoạn `covered` của `met_broker_daily.sql` (mục 3.4): `e.broker_key = c.broker_key` (chính người đang chăm) và `e.event_date between a.fr_date and a.to_date` (trong thời gian được giao).

#### Kết quả tại as-of 15/05

| Tiểu khoản `9994000010` đóng góp vào | BRK003 (người cũ) | BRK009 (người mới) |
|---|---|---|
| `interactions_30d` | **+6** (việc BRK003 đã làm) | +3 |
| `cover30_den` | 0 (không còn chăm) | +1 |
| `cover30_num` | 0 | +1 (nhờ tương tác của chính BRK009 từ 13/05) |

Tổng toàn bộ tiểu khoản (probe `P-MG-COVERAGE`): BRK009 có `cover30 = 16/22 = 0,7273`, BRK003 có `7/7`.

#### Vì sao thiết kế như vậy

- **Không thưởng nhầm người mới.** COVER30 dùng để đánh giá người đang chịu trách nhiệm. Nếu cho kế thừa, người mới có thể không liên hệ khách nào trong gần một tháng mà vẫn đạt độ phủ cao nhờ công của người cũ.
- **Không xóa công của người cũ.** Tương tác là việc đã làm, nên vẫn nằm trong `interactions_30d` của BRK003. Cách nối là theo `broker_hk` của sự kiện, không theo người đang chăm.
- **Không phạt người cũ.** Tiểu khoản rời khỏi cả tử lẫn mẫu của BRK003, nên tỷ lệ của BRK003 không bị kéo xuống vì một tiểu khoản không còn thuộc trách nhiệm của họ.
