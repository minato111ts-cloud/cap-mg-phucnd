# Sổ kỹ thuật tầng Gold — CAP-MG

- **Phạm vi:** `finova-dbt/models/gold/` (schema `mart`), macro `macros/gold/gold.sql`, role đọc `finova_app`, test `tests/gold/` (dbt và pytest), câu hỏi kiểm `evidence/probes/`.
- **Căn cứ:** Bảng 70, 71, 72, 74, 75 của đề; Bảng 24 (tầng Gold), Bảng 25 (D-DQ, D-BANGCHUNG); E.8 (INV-SEM-*, REQ-SEM-*, T-GOLD-DAY); QT-TEN-MART, QT-NO-METRIC-VAULT.
- **Cập nhật:** 04/11/2026.

## GD-01: Gold gồm những bảng nào

Gold gồm 5 bảng:

- 4 bảng do Bảng 71 đặt tên: `dim_broker_org_daily`, `dim_account_care_daily`, `sec_visibility_daily`, `met_broker_daily`.
- 1 bảng chất lượng `dq_mg_daily`, theo D-DQ ở Bảng 25.

QT-TEN-MART cho phép các tiền tố `dim_`, `fact_`, `mart_` và `met_`. Hai tiền tố `sec_`, `dq_` không có trong quy ước này nhưng do chính đề đặt, và đề thắng tài liệu gốc (Phụ lục E).

CAP-MG không bắt buộc bảng `fact_`. Sự kiện tương tác là bất biến, không bị xóa, nên đọc thẳng `asof.nhl_broker_event`; không cần cặp mốc `ingested_ts` / `deleted_ingested_ts` của fact ở E.8.

Không dựng bảng tổng hợp theo đơn vị:
- TC-CAP-MG-ROLLUP cộng `met_broker_daily` theo chi nhánh trong test.
- Câu P-MG-RESTRUCT dùng một file SQL; đề cho phép cột `query` là tên model hoặc file SQL.

## GD-02: Khung T-GOLD-DAY

`dbt_project.yml`, mục `gold:` dùng chung cơ chế với BV:

- incremental append, `on_schema_change: fail`;
- hai pre_hook: `asof_session()` đặt mốc của ngày D, rồi `asof_day_delete()` xóa phần của D;
- không vật hóa table (REQ-SEM-NOTABLE), vì policy RLS phụ thuộc bảng.

`asof_day_delete()` thay cho `bv_day_delete()` cũ và dùng chung cho cả hai tầng.

**Nguồn đọc:**
- Gold đọc BV (PIT, bridge) và view as-of, không đọc raw vault, không dùng `now()`.
- Thuộc tính lấy qua con trỏ PIT nối với view as-of theo (khóa, `ingested_ts`).
- `dq_mg_daily` còn đọc staging và `ctrl.batch_log`, vì báo cáo theo lô.

**Runner:** với mỗi ngày D, chạy `cap_mg_bv` rồi `cap_mg_gold`. Full refresh dựng lại cả hai cho từng ngày giao dịch, ngày đầu kèm `--full-refresh`.

**`cap_mg_all` từ schema trống (D-DBT):** PASS 291, WARN 2 (DQ-MOCOI, GT-HUB-NOMASTER), ERROR 0 với một ngày D = 15/05. Selector loại unit test: unit test giả lập `{{ this }}` của model incremental cần bảng đã có để lấy kiểu cột; lần đầu chạy, 4 unit test lỗi kéo 73 node phía sau bị bỏ qua. Unit test chạy sau bằng `dbt test --select test_type:unit` (11 PASS).

**Selector:** chế độ chọn test eager sẽ kéo một test vào bất kỳ selector nào chọn một model cha của nó. Test Gold đọc staging, raw, BV, nên `cap_mg_staging`, `cap_mg_raw`, `cap_mg_bv`, `cap_mg_asof` đều loại tag `gold`. Đây là cùng lý do `cap_mg_raw` loại `dv_bv`.

**Hiệu năng:**
- Lần đầu, bước Gold mất khoảng 24 giây mỗi ngày. Nguyên nhân là CTE phân công bị inline vào `exists`, nên view `asof.sat_reaflnk__flex` (có subquery tương quan lên `sts`) bị tính lại theo từng dòng.
- Trong lúc đó `sec_visibility_daily` chờ khóa: post_hook của nó phải `alter table dim_account_care_daily`, trong khi `met_broker_daily` vẫn đang đọc bảng này.
- Ép CTE `as materialized` thì bước Gold còn khoảng 1,5 giây mỗi ngày.

## GD-03: Logic từng bảng

| Bảng | Grain | Logic chính |
|---|---|---|
| `dim_broker_org_daily` | (business_date, broker_key) | Hồ sơ qua `pit_broker_daily`. Đường dẫn cây là tổ tiên trong `bridge_regrp_ancestor` của D, xếp theo depth giảm dần. `branch_id` là phần tử thứ 2 của đường dẫn (đơn vị ngay dưới gốc), không theo `grplevel`, nên G4 đổi chi nhánh (TH-TAICAUTRUC) và nhánh UNKNOWN (DEC-CAP-MG-ORPHAN) đều đúng. `work_status`: ACTIVE / LEFT / NOT_STARTED (DEC-CAP-MG-GAP) |
| `dim_account_care_daily` | (business_date, account_id) | Mọi tiểu khoản hệ thống biết tại cutoff(D), qua REAFLNK hoặc NAV của D. Môi giới theo `bridge_account_broker`; `broker_key` là người đang mang mã tại D. `care_basis` = `NO_ASSIGNMENT`, hoặc `REAFLNK` kèm `+DEC-CAP-MG-OVERLAP`, `+DEC-CAP-MG-GAP` |
| `sec_visibility_daily` | (business_date, viewer_id, account_id) | Phạm vi trong `org_roles` khớp với `scope_ids` của môi giới chăm sóc (mã môi giới và mọi đơn vị trên đường dẫn của D). Loại phạm vi suy từ chính mã, không viết cứng tên vai trò |
| `met_broker_daily` | (business_date, broker_key) | Mọi môi giới trong hồ sơ as-of D, kể cả người có 0 tiểu khoản. Định nghĩa chỉ số ở GD-04 |
| `dq_mg_daily` | (as_of_date, batch_id, source_table, reason_code) | Xem GD-06 |

## GD-04: Chỉ số (Bảng 72) và registry ngữ nghĩa

Registry nằm ở `meta.metric` của các cột trong `_gold__models.yml`: mã, kiểu, định nghĩa, giá trị khi không có dữ liệu.

- **`n_accounts`** (tiểu khoản chăm sóc, state): số dòng của `dim_account_care_daily` mang `broker_key` của người đó.
- **`book_nav`** (CAP-MG-BOOKNAV, state):
  - Σ NAV ngày D qua con trỏ `pit_account_daily`, `coalesce(…, 0)` (REQ-SEM-NULLCOMP).
  - Tiểu khoản chưa có NAV của D thì đếm ở `n_accounts_without_nav`. Dữ liệu đề có 0 tiểu khoản như vậy.
- **`interactions_30d`** (flow):
  - Sự kiện hợp lệ có ngày trong khoảng D−29…D.
  - Ngày sự kiện phải nằm trong `[join_date, leave_date]` của người mang mã (DEC-CAP-MG-BROKERKEY).
  - Gồm cả tương tác DQ-QUYEN (DEC-CAP-MG-INTER30).
- **`cover30_num` / `cover30_den`** (CAP-MG-COVER30, ratio):
  - Tử: tiểu khoản được chăm sóc tại D có tương tác của chính người đó trong 30 ngày, vào ngày người đó đang được giao tiểu khoản theo phân công hệ thống biết tại cutoff(D).
  - Mẫu: `n_accounts`.
  - Lưu riêng tử và mẫu để cấp trên cộng tử, cộng mẫu rồi mới chia.
- **`kpi_target_calls`, `kpi_batch_id`:** phiên bản chỉ tiêu do `pit_broker_daily` trỏ tới tại cutoff(D) (TH-NHAPTAY). Lô của phiên bản tra ở `ctrl.batch_log` theo (`source_table`, `ingested_ts`).
- **`calls_qtd`** (flow): sự kiện `CALL` (mã trong danh mục `event_type.csv`) từ đầu quý tới D, trong khoảng làm việc.

Không có chỉ số "hiện tại": mọi dòng mang `as_of_date`, `cutoff_ts` (INV-SEM-ASOF).

## GD-05: RLS

- **Role đọc:** `finova_app` theo DEC-CAP-MG-RLSROLE.
  - Chỉ có `USAGE` trên `mart`; `SELECT` cấp bằng `grants` của dbt cho 4 bảng của Bảng 71.
  - Policy `for select to finova_app`; người xem đặt `finova.viewer_id`.
- **Thứ tự dựng:**
  - Bảng nào cũng bật RLS trong post_hook của chính nó. Bảng đã bật mà chưa có policy thì role đọc không thấy dòng nào, tức là đóng khi lỗi.
  - Policy của `dim_account_care_daily` đọc `sec_visibility_daily`, nên tạo trong post_hook của `sec_visibility_daily`, vì bảng này dựng sau.
- **Hàm `mart.viewer_scopes()`:** `security definer`, đọc `ref_org_roles`, nên role đọc không cần quyền trên `staging`. Tạo lại mỗi lần dựng `dim_broker_org_daily`.
- **Policy lồng nhau:**
  - Policy của `met_broker_daily` đọc `dim_broker_org_daily`.
  - Policy của `dim_account_care_daily` đọc `sec_visibility_daily`.
  - Cả hai truy vấn con chịu RLS của bảng được đọc, nên tự lọc theo người xem.

## GD-06: Bảng chất lượng `dq_mg_daily` (D-DQ)

**Lô của ngày D:**
- Lô có `ingested_ts` trong (cutoff của ngày giao dịch liền trước, cutoff(D)]. Lô sự kiện cuối tuần vì vậy vào ngày giao dịch kế tiếp.
- Lô không nạp (`SKIPPED_DUP`, `REJECTED_BATCH`) không có `ingested_ts`, nên xếp theo `business_date`.
- Với mỗi lô dùng dòng sổ cuối, vì lô của KT-22 có hai dòng sổ.

**Số dòng:**
- `rows_landing` = `batch_log.rows_loaded`.
- `rows_valid` và `rows_rejected` đếm từ view staging hợp lệ và view `__rejected`.

**Mỗi lỗi một dòng.** `key_count` là số khóa bị ảnh hưởng; `key_sample` là tối đa 5 khóa mẫu, khóa rỗng thì thay bằng số dòng nguồn. Các nguồn lỗi:
- `reason_code` của view `__rejected`, tức các dòng bị loại hoặc sửa bằng cách khử trùng;
- cờ không loại dòng:
  - `FUTURE_TS_FIXED` (DQ-TUONGLAI);
  - `PARENT_MISSING` (DQ-MOCOI, xét trong cùng bản chụp);
  - `ASSIGNMENT_OVERLAP` (DQ-CHONGLAN: hai môi giới, khoảng hiệu lực giao nhau, trong cùng bản chụp);
  - `KEY_REUSED` (DQ-KHOA-TAISUDUNG: mã môi giới mang JOINDATE khác phiên bản trước);
  - `EVENT_NOT_ASSIGNED` (DQ-QUYEN, theo phân công hệ thống biết tại cutoff(D));
- `reason_code` của sổ nạp với lô không nạp (`DUP_CONTENT`, lỗi file).

Lô không có lỗi có một dòng với `reason_code` NULL.

**Ánh xạ mã:** từ `reason_code` sang mã DQ, hướng xử lý (`handling`) và `test_id` nằm ở seed `ref_dq_reason.csv`, là danh mục cấu hình chứ không rải trong SQL.

**Đối chiếu với dữ liệu đề:** tổng `rows_landing` 5.959, tổng `rows_rejected` 39 (bằng `ctrl.reject_count`), đủ 104 lô. Báo cáo theo ngày và giải thích từng mã lỗi ở `docs/chatluong.md`.

**Test đối chiếu `test_gold_dq_recon`:** mỗi lô thuộc đúng một ngày, là ngày giao dịch đầu tiên có cutoff ≥ `ingested_ts` (lô không nạp thì theo `business_date`). Lô có mặt thì chỉ được ở ngày đó (`WRONG_DAY`); ngày đó đã dựng thì lô phải có mặt (`MISSING_BATCH`). Bản đầu đòi mọi lô có `ingested_ts` ≤ cutoff lớn nhất phải có mặt, nên đỏ 99 khi `cap_mg_all` chỉ dựng một ngày.

**T-GUARD:** lô bị chặn mà chưa được full refresh xử lý nằm ngoài mọi cửa sổ theo ngày, nên được phép vắng. Sau full refresh, lô vào đúng ngày theo `ingested_ts`. Vì vậy test T-GUARD so vault, BV, Gold trừ `dq_mg_daily`, rồi kiểm riêng rằng `dq_mg_daily` có thêm đúng dòng của lô giả.

## GD-07: Test và phép thử âm

| Mã | Test | Phép thử âm | Kết quả |
|---|---|---|---|
| Grain (Bảng 24) | `dv_unique_combination` × 5 bảng | Bỏ `distinct on (account_hk)` ở tập tiểu khoản | Đỏ 200 |
| Không cột định danh (GT-STG-PII) | `dv_shape` × 5 bảng | Thêm `email_masked` vào `dim_broker_org_daily` | Đỏ 1 cột |
| Tổng khớp vault (Bảng 24) | `test_gold_vault_totals.sql` | `book_nav` bỏ con trỏ PIT, cộng NAV mọi ngày ≤ D | Đỏ 2 (ACCOUNTS, BOOKNAV ngày 05/05) |
| TC-CAP-MG-ROLLUP | `test_tc_cap_mg_rollup.sql` | Theo đề: dùng cây ngày cuối (15/05) cho ngày 29/04 | Đỏ 2 (CN1, CN2) |
| TC-CAP-MG-RLS | `tests/gold/test_rls.py` | Theo đề: cho BRK003 xem tiểu khoản của BRK009, ngày 11/05 | Đỏ, thừa `9994000001…` |
| D-DQ khớp sổ | `test_gold_dq_recon.sql` | Bỏ dòng `DUPLICATE_EVENT` của `__rejected` | Đỏ 1 (lô `CAP-MG-0060`) |
| REBUILD (QT-DAY-REBUILD) | grain và PT-FULL | Bỏ `asof_day_delete` khỏi pre_hook của Gold, dựng lại 05/05 | Đỏ (24 môi giới, 5 lô trùng) |

**Hai lần xanh suông đã phát hiện và sửa:**
- Phép thử tổng khớp vault lần đầu chỉ bỏ điều kiện `business_date`. Phép nối theo con trỏ `ingested_ts` vẫn chỉ lấy NAV của ngày D, nên phép thử không làm sai số. Lần thứ hai bỏ hẳn con trỏ thì test đỏ.
- `dq_mg_daily` lần đầu lọc lô theo `ingested_ts`, nên bỏ sót 41 lô `SKIPPED_DUP`. Test `MISSING_BATCH` cũng lọc theo `ingested_ts` nên vẫn xanh. Sau khi sửa cả hai, bảng có đủ 104 lô.

## GD-08: Câu hỏi kiểm

Mỗi câu hỏi kiểm là một file SQL thuần ở `evidence/probes/`, trả `as_of` và `value`. `runner/probes.py` chạy các file đó bằng role `finova_dbt` và ghi `evidence/probes.csv`, nên trainer chạy lại đúng file và không có số chép tay. Số tiền ghi đủ đồng (`trim_scale`), tỷ lệ ghi dạng tử/mẫu.
