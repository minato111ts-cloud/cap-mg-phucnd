# Ma trận test — CAP-MG (D-TEST)

- **Cập nhật:** 06/11/2026, nhánh `feat/cap-mg-phucnd`
- **Phạm vi:** loader (landing, ctrl), staging, raw vault, as-of, Business Vault, Gold và đầu cuối (TC-CAP-E2E).
- **Cách chạy:** `uv run --env-file .env dbt build --selector cap_mg_staging --project-dir finova-dbt --profiles-dir finova-dbt` và `uv run --env-file .env pytest -q`. Raw vault: `python -m runner.run`, `dbt test --select test_type:unit`, và `RUN_PT_FULL=1 pytest -q tests/raw` (xem phần raw vault).
- **Phép thử âm:** cố ý làm hỏng code hoặc dữ liệu để chứng minh test đỏ, rồi khôi phục. Phép thử cần sửa dữ liệu chạy trên bản sao `cap_mg_phucnd_negtest`, không đụng database thật. Cột "Nơi chạy" ghi *máy thật* (PostgreSQL 16 cục bộ). Các phép thử trước đây ghi *thay thế* (môi trường mô phỏng trước 02/11/2026) đã chạy lại trên máy thật ngày 06/11/2026, số đỏ giữ nguyên.

## Ma trận phủ (D-TEST)

Mỗi lỗi và tình huống của đề: test nào, ở tầng nào, kết quả trên dữ liệu đề. Phép thử âm của từng test ghi ở mục tầng tương ứng bên dưới.

### Lỗi dữ liệu (Bảng 67)

| Mã | Hướng xử lý | Tầng | Test | Kết quả |
|---|---|---|---|---|
| DQ-NGAY-SAI | LOAI | Staging | `test_dq_ngay_sai_stays_out_of_valid_view`, GT-STG-RECON | Xanh; 10 dòng `INVALID_DATE_RANGE` ở `__rejected` |
| DQ-MOCOI | CANHBAO | Staging, raw vault | `test_stg_regrp_parent_missing` (warn), GT-HUB-NOMASTER (warn) | Warn 2 dòng (G7 → CN9); warn 1 khóa (CN9) |
| DQ-VONG | LOAI | Staging, Business Vault | `test_stg_regrp_no_cycle`, TC-CAP-MG-TREE, `test_cycle_rows_never_reach_vault` | Xanh; 2 dòng `CYCLE_DETECTED` (G5, G6) |
| DQ-CHONGLAN | QUYETDINH | Business Vault | TC-CAP-MG-ONEBROKER | Xanh; 3 tiểu khoản × 5 ngày phân xử cho BRK021 |
| DQ-KHOA-TAISUDUNG | QUYETDINH | Staging, raw vault, Gold | `test_stg_broker_hk_consistent`, `test_broker_code_reuse_versions`, `test_dec_brokerkey_new_holder_has_no_old_interactions` | Xanh; BRK017 có 1 khóa hub, 3 phiên bản hồ sơ |
| DQ-TRUNG-NGUYEN | SUA | Staging | GT-STG-UNIQUE (`test_stg_dedup`) | Xanh; 12 dòng `DUPLICATE_EVENT` |
| DQ-TUONGLAI | SUA | Staging | TC-CAP-MG-EVENTTIME | Xanh; 6 dòng dùng `server_ts`, có cờ |
| DQ-KHOA-NULL | LOAI | Staging | `test_dq_khoa_null_stays_out_of_valid_view`, GT-STG-RECON | Xanh; 4 dòng `KEY_NULL` |
| DQ-MA-LA | LOAI | Staging | `test_dq_ma_la_stays_out_of_valid_view`, GT-STG-RECON | Xanh; 3 dòng `ALLCODE_UNKNOWN` |
| DQ-QUYEN | CANHBAO | Gold | `test_dq_quyen_not_in_cover30`, `test_dq_quyen_events_have_no_assignment` | Xanh; 7 tương tác, không vào tử COVER30 |
| DQ-EXCEL | SUA | Loader, staging | TC-CAP-MG-EXCEL, `test_tc_cap_ldz_06_spreadsheet_physical_tracing` | Xanh |
| DQ-CHUADUYET | LOAI | Staging, Gold | TC-CAP-MG-EXCEL, `test_th_nhaptay_rejected_rows_have_no_target` | Xanh; 6 dòng `UNAPPROVED_ROW` |
| DQ-CONGTHUC | LOAI | Staging, Gold | TC-CAP-MG-EXCEL, `test_th_nhaptay_rejected_rows_have_no_target` | Xanh; 2 dòng `FORMULA_ERROR` |
| DQ-PII (cột định danh) | CANHBAO | Staging, Gold | GT-STG-PII, `dv_shape` của 5 bảng Gold | Xanh |
| DQ-FILE-HONG | TUCHOI_LO | Loader | `test_tc_cap_ldz_02_negative_physical_integrity` | Gói đề không có lô hỏng; test dựng lô hỏng, xanh |

### Tình huống (Bảng 68 và tình huống chung tìm thấy trong đề)

| Mã | Tầng | Test | Kết quả |
|---|---|---|---|
| TH-HIEULUCTUONGLAI | As-of | TC-CAP-MG-FUTUREEFF, P-MG-REASSIGN | Xanh; 08/05 có 15 phân công đã biết chưa tới hiệu lực |
| TH-LUIHIEULUC | As-of | TC-CAP-MG-BACKDATE, P-MG-BACKDATE | Xanh; 28/04 giữ BRK005 |
| TH-TAICAUTRUC | Raw vault, Gold | `test_esat_regrp_parent_g4_switch`, TC-CAP-MG-ROLLUP, P-MG-RESTRUCT | Xanh; G4 từ CN2 sang CN1 ở 04/05 |
| TH-NGHIVIEC | Gold | `test_th_nghiviec_flag_follows_work_status`, `test_th_nghiviec_accounts_move_to_successor`, P-MG-REUSE | Xanh; 13 tiểu khoản về BRK018. Dữ liệu đề không có ngày giao dịch trong khoảng trống; cờ được kiểm bằng tình huống giả |
| TH-CHONGLAN | Business Vault | TC-CAP-MG-ONEBROKER, P-MG-OVERLAP | Xanh |
| TH-NHAPTAY | Business Vault, Gold | `test_th_nhaptay_kpi_version_by_cutoff`, `test_th_nhaptay_v2_replaces_v1_target`, GT-BV-PTR, P-MG-KPI | Xanh; v1 từ 21/04, v2 từ 06/05 |
| TH-RLS | Gold | TC-CAP-MG-RLS | Xanh |
| TH-GUILAI | Loader | `test_tc_cap_ldz_03_idempotency_and_duplicate_content` | Xanh; 41 lô `SKIPPED_DUP` |
| TH-ABA | Loader, raw vault | `test_tc_cap_ldz_03b_snapshot_revert_is_loaded`, PT-ABA | Xanh; `CAP-MG-0032`, `CAP-MG-0066` được nạp |
| TH-VANGMAT | Raw vault | `test_sts_regrp_g7_deleted_at_cap_mg_0032`, `ut_sts_snapshot_absence` | Xanh; G7 `DELETED` |
| TH-DINHCHINH | Raw vault | PT-REVDATE (3 unit test) | Gói đề không có; unit test dựng tình huống, xanh |
| TH-DAOTHUTU | Raw vault | `test_t_guard_*` (3 test) | Gói đề không có; lô giả trong pytest, xanh |
| TH-VEMUON | Loader, runner | Không có test riêng | Gói đề không có: `available_ts = commit_ts` ở cả 104 dòng manifest |

## Staging: test singular (`finova-dbt/tests/staging/`)

| Mã | File | Mức | Kiểm gì | Phép thử âm | Kết quả | Nơi chạy |
|---|---|---|---|---|---|---|
| GT-STG-RECON | `test_stg_reconciliation.sql` | error | Theo từng lô: `batch_log.rows_loaded` = dòng landing = hợp lệ + bị loại | Thêm `and source_row_no <> 1` vào `stg_flex__broker` | Đỏ 3 lô | máy thật |
| GT-STG-KEYTS | `test_stg_keyts.sql` | error | Không có hai dòng hợp lệ cùng (khóa, `ingested_ts`) khác hashdiff | Chèn lô `CAP-MG-9999` cùng `ingested_ts` với `CAP-MG-0002`, BRK001 khác email; gom xung đột theo `batch_id` | Đỏ 1 khóa | máy thật |
| GT-STG-UNIQUE | `test_stg_dedup.sql` (`DUP_KEPT_TWICE`) | error | Mỗi (`ingested_ts`, khóa) tối đa một dòng hợp lệ | Xóa nhánh `_dup_rank > 1` ở `stg_finova_app__events` | Đỏ 12 khóa (`CAP-MG-0060`); KEYTS, RECON xanh | máy thật |
| GT-STG-UNIQUE | `test_stg_dedup.sql` (`DUP_NOT_IDENTICAL`) | error | Dòng loại vì trùng phải cùng hashdiff với dòng được giữ | Chèn BRK001 khác email cùng lô; xóa nhánh `_has_conflict` ở `stg_flex__broker` | Đỏ 1; KEYTS xanh | máy thật |
| GT-STG-PII | `test_stg_pii.sql` | error | Cột định danh không ra staging ở dạng rõ | Bỏ che `mobile_masked` | Đỏ 72 dòng | máy thật |
| TC-CAP-MG-EVENTTIME | `test_stg_events_event_time.sql` | error | Giờ thiết bị lệch tương lai quá ngưỡng thì dùng `server_ts` và có cờ; staging khớp landing | Ngưỡng 10 ngày qua `--vars` | Đỏ 6 dòng | máy thật |
| TC-CAP-MG-EXCEL | `test_stg_kpi_excel.sql` | error | KPI là số; ô lỗi công thức vào `FORMULA_ERROR`; dòng chưa duyệt bị loại | Đọc Excel với `header_rows: 1` | `test_tc_cap_mg_excel_negative_single_header_row` xanh ở mọi lần pytest | máy thật |
| DEC-CAP-MG-BROKERKEY | `test_stg_broker_hk_consistent.sql` | error | Cùng mã môi giới cùng `broker_hk` ở 4 nguồn | Reaflnk băm mã không có `'FLEX'` | Đỏ 1306 dòng | máy thật |
| DQ-VONG | `test_stg_regrp_no_cycle.sql` | error | Cây hợp lệ không có vòng mọi độ dài | Bỏ nhánh `CYCLE_DETECTED` | Đỏ 2 nút (G5, G6) | máy thật |
| GT-NHL-CONTENT | `test_stg_nhl_content.sql` | error | Mọi dòng hợp lệ cùng khóa nhl ở mọi lô có cùng nội dung | DB thử: chèn lô gửi lại một `event_id`, đổi `duration_sec` | Đỏ 1 khóa | máy thật |
| DQ-MOCOI | `test_stg_regrp_parent_missing.sql` | warn | Đơn vị trỏ tới cha không có trong bản chụp | Đổi severity sang error | Warn 2 (G7 → CN9) | máy thật |
| null_and_count | `test_stg_attr_nulled.sql` | warn | Ô có giá trị ở landing nhưng NULL ở view hợp lệ (10 cột thuộc tính) | `GRPID = 'X1'`, `raw_event_ts = '20/04/2026 9h'` | Warn 2 ô | máy thật |

## Staging: test cột (`finova-dbt/models/staging/schema.yml`)

- `not_null` (error) trên mọi khóa băm `*_hk`, hashdiff `sat_*_hd`/`nhl_*_hd`, `ingested_ts`, `event_ts`, `is_future_ts_fixed`, `is_device_ts_invalid`, các cột dựng quan hệ (`fr_date`, `to_date`, `tx_date`, `nav`) và `reason_code` của 6 view `__rejected`.
- `not_null` (warn) trên thuộc tính được phép thiếu: `grplevel` (regrp), `join_date`, `grpid` (broker). Phép thử âm của `grpid`: `GRPID = 'X1'` ở DB thử → warn 1 (máy thật).

## Staging: pytest (`tests/staging/`)

GT-STG-RECON chỉ cân tổng. Bỏ quy tắc loại thì dòng lỗi lọt sang view hợp lệ, tổng vẫn khớp: ba phép thử âm dưới đây cho `dbt build --selector cap_mg_staging` xanh hoàn toàn (PASS 75, WARN 1), chỉ pytest đỏ. Vì vậy `test_reject_rules.py` là test thật của ba lỗi này, không phải GT-STG-RECON.

| Mã | File | Kiểm gì | Phép thử âm | Kết quả | Nơi chạy |
|---|---|---|---|---|---|
| DQ-NGAY-SAI | `test_reject_rules.py` | View hợp lệ không có `to_date < fr_date`; 10 dòng `INVALID_DATE_RANGE` | Bỏ nhánh `INVALID_DATE_RANGE` ở `stg_flex__reaflnk` | Đỏ | máy thật |
| DQ-MA-LA | `test_reject_rules.py` | `event_type` của view hợp lệ đều có trong danh mục; 3 dòng `ALLCODE_UNKNOWN` | Bỏ nhánh `ALLCODE_UNKNOWN` ở `stg_finova_app__events` | Đỏ | máy thật |
| DQ-KHOA-NULL | `test_reject_rules.py` | View hợp lệ không có `broker_id` NULL; 4 dòng `KEY_NULL` | Bỏ `broker_id is null` khỏi nhánh `KEY_NULL` | Đỏ | máy thật |
| TC-NEN-HASH-TZ | `test_hash_tz.py` | Mọi cột băm của staging không đổi khi phiên đổi `TimeZone`/`DateStyle` | `dv_fmt_val` dùng `::text` cho timestamptz | Đỏ ở `nhl_broker_event_hd` | máy thật |

## Loader: pytest (`tests/loader/test_loader.py`)

| Test | Kiểm gì |
|---|---|
| `test_tc_cap_ldz_01_spec_invariants_system_columns` | INV-T6: mọi `source_id` có trong `ctrl.source_system` với `is_simulated_ts = true`; INV-T1: 5 cột hệ thống NOT NULL, `record_hash` bytea 32 byte |
| `test_tc_cap_ldz_02_negative_physical_integrity` | File thiếu, sai SHA-256, sai số dòng → `REJECTED_BATCH` |
| `test_tc_cap_ldz_03_idempotency_and_duplicate_content` | Nạp lại → `ALREADY_LOADED`; gửi lặp nội dung → `DUP_CONTENT` |
| `test_tc_cap_ldz_03b_snapshot_revert_is_loaded` | KT-22: bản chụp quay về nội dung cũ (A → B → A) vẫn `LOADED`; chỉ trùng lô gần nhất mới `DUP_CONTENT`. Phép thử âm: so với mọi lô LOADED → đỏ (máy thật) |
| `test_tc_cap_ldz_04_schema_drift_resilience` | Cột mới → thêm cột NULL, ghi `ctrl.schema_drift` |
| `test_tc_cap_ldz_05_inv_t1_load_reject_missing_event_ts` | Dòng không tính được `event_ts` → `ctrl.load_reject` (INV-T1) |
| `test_tc_cap_ldz_06_spreadsheet_physical_tracing` | Dấu vết dòng/cột Excel (`excel_row_no`, `source_col_map`) |
| `test_tc_cap_ldz_07_contract_driven_mock_contract` | Loader chạy theo hợp đồng giả, không ghi cứng tên bảng |
| `test_tc_cap_mg_excel_real_file_headers` / `..._negative_single_header_row` | TC-CAP-MG-EXCEL: tiêu đề hai dòng của file thật; phép thử âm một dòng tiêu đề |
| `test_event_ts_future_guard_uses_threshold` | Quy tắc `event_ts` tương lai đọc ngưỡng từ `thresholds.yaml` |
| `test_thresholds_in_sync_with_dbt_vars` | INV-M6: ngưỡng ở `dbt_project.yml` bằng `thresholds.yaml` |
| `tests/loader/test_ingested_ts.py::test_tc_cap_ldz_ingested_ts_equals_commit_ts` | Bảng 24 (landing): mỗi lô LOADED có `batch_log.ingested_ts` bằng `commit_ts` của đúng dòng manifest đã nạp (theo `arrival_seq`), và mọi dòng landing của lô mang đúng giá trị đó. Phép thử âm (`negtest`): lệch `ingested_ts` một dòng `landing.ref_nav` 1 giây -> đỏ ở `CAP-MG-0004` |

## Raw vault: test chung theo loại bảng (`finova-dbt/models/atomic/raw/_raw__models.yml`)

Sinh cho 19 bảng, tổng 160 data test (cùng các test singular dưới đây). Generic test tự viết ở `finova-dbt/tests/generic/dv_tests.sql`, vì project không dùng dbt_utils.

| Mã | Áp cho | Cách kiểm | Mức |
|---|---|---|---|
| GT-HUB-UNIQ | hub | `unique(hk)`, `dv_unique_combination(bkcc, bk)` | error |
| GT-HUB-BKCC | hub | `relationships` tới seed `ref_bkcc` (FLEX, FINOVA_APP) | error |
| GT-HUB-SHAPE, GT-LNK-SHAPE | hub, link | `dv_shape`: cột thực tế đúng bằng danh sách cho phép (information_schema) | error |
| GT-LNK-UNIQ | link, nhl | `unique(link_hk)`, `dv_unique_combination` trên khóa hub (+ event_id với nhl) | error |
| GT-LNK-PARENT, GT-SAT-PARENT | link, nhl, sat, esat, sts | `relationships` tới hub hoặc link cha | error |
| GT-SAT-PK | sat, esat, sts | `dv_unique_combination(khóa cha[, business_date], ingested_ts)` | error |
| GT-SAT-NOREDUNDANT | sat, esat | `dv_sat_no_redundant` (lag hash_diff) | warn |
| GT-STS-ENUM | sts | `accepted_values` ACTIVE/DELETED + `test_raw_sts_transitions` | error |
| GT-TS-NOTNULL | mọi bảng | `not_null` ingested_ts, event_ts | error |

Phép thử âm sửa dữ liệu, chạy trên bản sao `cap_mg_phucnd_negtest` của DB thử (máy thật, 03/11/2026). Trước khi sửa, `dbt test --select hub_regrp hub_broker link_reaflnk`: PASS 42, WARN 1, ERROR 0.

| Mã | Phép thử âm | Kết quả |
|---|---|---|
| GT-HUB-BKCC | Chèn một khóa `hub_regrp` có `bkcc = 'XX'` | Đỏ 1: `relationships_hub_regrp_bkcc__bkcc__ref_ref_bkcc_` |
| GT-HUB-SHAPE | `alter table atomic.hub_broker add column broker_name text` | Đỏ 1: `dv_shape_hub_broker_...` |
| GT-LNK-SHAPE | `alter table atomic.link_reaflnk add column status text` | Đỏ 1: `dv_shape_link_reaflnk_...` |

Thêm ngày 06/11/2026, trên bản sao database bằng chứng. Trước khi sửa, `dbt test --selector cap_mg_raw`: PASS 170, WARN 1, ERROR 0. Sau đó sửa dữ liệu một lượt rồi chạy lại:

| Mã | Phép thử âm | Kết quả |
|---|---|---|
| GT-LNK-UNIQ | Chèn lại một dòng `link_reaflnk` | Đỏ: `unique_link_reaflnk_link_reaflnk_hk`, `dv_unique_combination_link_reaflnk_...` |
| GT-LNK-PARENT | Chèn link có `broker_hk` không có trong hub | Đỏ: `relationships_link_reaflnk_broker_hk__...` |
| GT-SAT-PK | Chèn lại một dòng `sat_regrp__flex` | Đỏ: `dv_unique_combination_sat_regrp__flex_regrp_hk__ingested_ts` |
| GT-SAT-PARENT | Chèn dòng satellite có `regrp_hk` không có trong hub | Đỏ: `relationships_sat_regrp__flex_regrp_hk__...` |
| GT-SAT-NOREDUNDANT | Chèn phiên bản sau cùng `hash_diff` vào `sat_broker_profile__flex` | Warn 1: `dv_sat_no_redundant_sat_broker_profile__flex_broker_hk` |
| GT-TS-NOTNULL | Đặt `event_ts` NULL một dòng `nhl_broker_event` | Đỏ: `not_null_nhl_broker_event_event_ts` |

## Raw vault: test singular (`finova-dbt/tests/raw/`, tag `dv_raw`)

| Mã | File | Mức | Kiểm gì | Phép thử âm | Kết quả | Nơi chạy |
|---|---|---|---|---|---|---|
| GT-HUB-UNIQ | (test cột) | error | Hub không trùng khóa | Bỏ `not exists` ở `dv_load_hub`, chạy incremental `hub_broker` cửa sổ `(-infinity, hi]` | Đỏ 24 khóa (`unique`, `bkcc+bk`) | máy thật |
| GT-HUB-NOMASTER | `test_raw_hub_nomaster.sql` | warn | Khóa hub chưa có satellite của nguồn chủ (broker, regrp, reaflnk) | Không cần sửa: dữ liệu đề có sẵn khóa CN9 | Warn 1 (CN9, khớp DQ-MOCOI) | máy thật |
| GT-ESAT-ONEACTIVE | `test_raw_esat_oneactive.sql` | error | Tại mọi thời điểm ghi, mỗi driving key tối đa một link hiệu lực | Bỏ nhánh đóng link cũ ở `dv_load_esat_dk`, build full refresh | Đỏ 1 (G4 từ `CAP-MG-0051`) | máy thật |
| GT-STS-ENUM | `test_raw_sts_transitions.sql` | error | Hai dòng sts liền nhau khác trạng thái; dòng đầu không phải ACTIVE | Bỏ so trạng thái trước ở `dv_load_sts_snapshot` | Đỏ 75 dòng | máy thật |
| Đủ dòng | `test_raw_completeness.sql` | error | Khóa staging (≤ hi_ts) có trong hub/link/nhl; phiên bản cuối của satellite bằng hashdiff dòng staging cuối | `dv_load_sat` chỉ ghi phiên bản đầu mỗi khóa | Đỏ 4 satellite | máy thật |

Test đủ dòng không bắt lỗi ghi sai `ingested_ts` mà phiên bản cuối vẫn đúng: thử đổi `lag` sang sắp ngược thời gian thì test vẫn xanh. Lỗi loại đó do PT-ABA và PT-FULL bắt.

## Raw vault: dbt unit test (`_raw__unit_tests.yml`)

Chạy bằng `dbt test --select test_type:unit` lúc phát triển. Runner không chạy unit test (RV-08). Phép thử âm sửa `macros/raw/dv_load.sql` rồi khôi phục đúng từng byte (máy thật, 03/11/2026). Fixture khóa băm dạng bytea hex; `expect` chỉ dùng cột text, vì dbt so bytea như object Python.

| Mã | Unit test | Kiểm gì | Phép thử âm | Kết quả |
|---|---|---|---|---|
| PT-ABA | `ut_sat_aba_three_versions` | A → B → A trong một cửa sổ ra 3 phiên bản | Khử trùng theo (khóa, hash_diff), bỏ `ingested_ts` | Đỏ (ra 2 phiên bản) |
| T-SAT | `ut_sat_first_row_compares_with_vault` | Dòng đầu cửa sổ trùng phiên bản trong vault thì không ghi | Dòng đầu không so với vault (`seq.prev_hd` thay cho `coalesce(seq.prev_hd, cur.hash_diff)`) | Đỏ, cùng `ut_sat_day_revdate_older_date_after_newer` |
| PT-IDEMP | `ut_sat_rerun_window_adds_nothing` | Chạy lại cửa sổ đã nạp không thêm dòng | Dùng SQL mẫu của đề: so phiên bản mới nhất, bỏ `not exists` | Đỏ (RV-02) |
| PT-ESAT-SWITCH | `ut_esat_switch_in_window`, `ut_esat_switch_against_vault` | Đổi link: một dòng đóng, một dòng mở, cùng ingested_ts; link hiệu lực lấy từ vault | Bỏ nhánh đóng link cũ | Đỏ cả hai |
| T-STS bản chụp | `ut_sts_snapshot_absence` | Vắng → DELETED, có lại → ACTIVE, dòng `__rejected` tính là có mặt | Bỏ nhánh `__rejected` | Đỏ |
| PT-REVDATE | `ut_sat_day_revdate_older_date_after_newer` | NAV ngày 05/05 về sau ngày 06/05, cùng giá trị: vẫn ghi 05/05; 06/05 gửi lại không ghi | Dòng đầu cửa sổ so với phiên bản mới nhất của khóa, bỏ `business_date` | Đỏ (mất dòng 05/05) |
| PT-REVDATE | `ut_sat_day_revdate_in_window` | Trong một cửa sổ: 06/05 trước, 05/05 sau rồi đính chính: 3 phiên bản | `lag` chỉ chia theo khóa cha | Đỏ |
| PT-REVDATE | `ut_nhl_revdate_older_event_after_newer` | Sự kiện cũ về sau sự kiện mới vẫn được ghi; sự kiện đã có không ghi lại | Lọc `event_ts >` mốc lớn nhất trong vault | Đỏ |

## Raw vault: pytest (`tests/raw/test_raw_vault.py`)

`RUN_PT_FULL=1` thì dựng DB thử `<CAP_DBNAME>_ptfull` (bootstrap, ctrl, runner 19 ngày), mất khoảng 7 phút. Không đặt thì phần số liệu kiểm chạy trên `CAP_DBNAME` nếu runner đã chạy ở đó, ngược lại bỏ qua.

| Mã | Test | Kiểm gì |
|---|---|---|
| PT-IDEMP | `test_pt_idemp_rerun_windows` | Chạy lại cửa sổ cuối 2 lần và cửa sổ `(-infinity, hi]` không full refresh: số dòng và md5 của 19 bảng không đổi |
| PT-FULL, GT-BV-REBUILD | `test_pt_full_matches_daily` | Runner `--full-refresh` (raw một cửa sổ, BV và Gold dựng lại từng ngày) cho cùng số dòng, md5 như chạy 19 ngày, ở 19 bảng raw, 4 bảng BV và 5 bảng Gold |
| TC-CAP-MG-BACKDATE | `test_tc_cap_mg_backdate` | Phân công hiệu lực của từng ngày đọc lại sau khi nạp đủ mọi lô bằng kết quả chụp ngay sau lần chạy của ngày đó; có ít nhất một ngày mà điều biết sau này khác (test không xanh suông) |
| Runner | `test_runner_daily_runs`, `test_runner_no_failed_run` | DB thử: đủ 19 lần chạy theo ngày, đều SUCCESS; mọi DB: không lần nào FAILED hay RUNNING |
| DQ-VONG, sts | `test_sts_regrp_g7_deleted_at_cap_mg_0032` | sts_regrp chỉ có G7 DELETED ở `CAP-MG-0032`; G5/G6 bị loại ở `CAP-MG-0061` không bị xóa giả |
| TH-TAICAUTRUC | `test_esat_regrp_parent_g4_switch` | G4: CN2 mở ở `CAP-MG-0001`; CN2 đóng và CN1 mở ở `CAP-MG-0051` |
| DEC-CAP-MG-CYCLE | `test_cycle_rows_never_reach_vault` | Không phiên bản nào có G5 → G6 hay G6 → G5 |
| DEC-CAP-MG-BROKERKEY | `test_broker_code_reuse_versions` | BRK017: 1 khóa hub, 3 phiên bản hồ sơ (người cũ, nghỉ việc, người mới `BRK017:2026-05-11`) |
| DEC-ELT-REJECT | `test_reject_count_matches_rejected_views` | `ctrl.reject_count` của các lần chạy theo ngày bằng số dòng thật của mọi view `__rejected` theo (lô, view, reason_code), mỗi lô ở đúng một lần; full refresh đếm lại đủ |
| T-GUARD | `test_t_guard_blocks_replayed_batch` | Phép thử âm: chèn lô LOADED mang giờ 22/04 sau lần chạy cuối, thì lần sau ghi `BLOCKED_BY_GUARD`; lô có ở `ctrl.guard_block`; chạy lại vẫn chặn, `v_guard_open` gộp 2 lần chặn; `runner.guard list` in lô và lệnh full refresh |
| T-GUARD | `test_t_guard_full_refresh_resolves_block` | Full refresh SUCCESS ghi `guard_resolution` FULL_REFRESH; lần sau không chặn; raw, BV, Gold không đổi, riêng `dq_mg_daily` có thêm đúng dòng của lô giả (ngày 22/04, báo theo sổ nạp) |
| T-GUARD | `test_t_guard_accept_lets_run_continue` | ACCEPTED không có lý do bị từ chối; có lý do thì lần sau SUCCESS |
| Runner | `test_runner_exception_marks_failed` | Phép thử âm: `run_dbt` ném exception thì `ctrl.batch_run` ghi `FAILED` kèm lỗi, không kẹt `RUNNING`; lần sau SUCCESS |

## As-of: pytest (`tests/asof/test_asof.py`)

View đọc cutoff từ GUC của phiên; dbt test không có hook đặt GUC trên connection của test nên dùng pytest (AB-08). Chỉ đọc, chạy trên `CAP_DBNAME`. Phép thử âm chạy trên `cap_mg_phucnd_negtest` ngày 03/11/2026, mỗi phép sửa tạm một chỗ rồi khôi phục.

| Mã | Test | Kiểm gì | Phép thử âm | Kết quả |
|---|---|---|---|---|
| TC-SLV-NOCUTOFF | `test_tc_slv_nocutoff` (8 view) | Phiên chưa đặt cutoff, hoặc đặt rồi xóa thành chuỗi rỗng: đọc view báo lỗi | `asof.cutoff()` trả `'infinity'` thay vì `raise` | Đỏ 8/8 view |
| PT-ASOF-SINGLE | `test_pt_asof_single` | 19 ngày × 8 view: số dòng = số khóa (khóa và ngày với NAV) | Bỏ `distinct on` trong `asof_latest` | Đỏ |
| PT-NOFUTURE | `test_pt_nofuture` | 19 ngày × 8 view: không dòng nào có `ingested_ts` sau cutoff(D) | Bỏ điều kiện `<= asof.cutoff()` trong `asof_latest`, `asof_known` | Đỏ |
| TC-CAP-MG-FUTUREEFF | `test_tc_cap_mg_futureeff` | Mọi phân công hiệu lực tại D có `fr_date <= D <= to_date`; dữ liệu có phân công đã biết mà chưa tới hiệu lực (08/05: 15) | Theo đề: `esat_reaflnk__flex` lọc theo `ingested_ts` thay vì FRDATE | Đỏ ở 10 ngày (04/05 → 15/05): 08/05 có 15 phân công `FRDATE > D`; các ngày đó còn có 13–35 phân công đã hết hạn |
| TC-CAP-MG-BACKDATE | `tests/raw`: `test_tc_cap_mg_backdate` | Xem mục Raw vault: pytest | Theo đề: dùng phân công mới nhất cho mọi ngày (bỏ `<= cutoff` trong `asof_latest`), cùng logic so với lần dựng đầu | 14/19 ngày lệch (17/04 → 08/05); khôi phục thì khớp |

## Business Vault (`finova-dbt/models/atomic/bv/_bv__models.yml`, `finova-dbt/tests/bv/`, tag `dv_bv`)

| Mã | Test | Mức | Kiểm gì | Phép thử âm | Kết quả |
|---|---|---|---|---|---|
| GT-BV-PTR | `test_bv_ptr.sql` | error | Con trỏ khác NULL của 2 PIT có phiên bản thật trong satellite; `ingested_ts` của con trỏ `<= cutoff_ts` (suy từ `as_of_date`, độc lập với GUC) | `asof_session` đặt cutoff muộn hơn 1 ngày, D = 05/05 | Đỏ 19 (con trỏ chỉ tiêu trỏ bản v2 nạp 06/05 16:30) |
| GT-BV-SHAPE | `dv_shape` × 4 model | error | Chỉ có các cột cho phép | Thêm cột `nav` vào `pit_account_daily` | Đỏ 1 cột |
| GT-BV-REBUILD | `tests/raw`: `test_pt_full_matches_daily` | error | Xem mục Raw vault: pytest | Bỏ `bv_day_delete` khỏi pre_hook rồi dựng lại 05/05 | Số dòng 4 bảng nhân đôi (24 → 48, 200 → 400, 200 → 400, 25 → 50); khôi phục thì md5 khớp |
| TC-CAP-MG-ONEBROKER | `tc_cap_mg_onebroker` (`dv_unique_combination` trên `bridge_account_broker`) | error | Mỗi (as_of_date, tiểu khoản) tối đa một môi giới | Theo đề: bỏ quy tắc DEC-OVERLAP (giữ mọi ứng viên), D = 05/05 | Đỏ 3 tiểu khoản |
| TC-CAP-MG-TREE | `test_tc_cap_mg_tree.sql` | error | Mỗi ngày đúng một gốc; mọi đơn vị trong `bridge_regrp_ancestor` có gốc là cấp trên; không đơn vị nào là cấp trên của chính nó | Theo đề: nạp cây có vòng, không lọc (bỏ `CYCLE_DETECTED` ở staging, dựng lại view staging và raw), D = 06/05 | Đỏ 4 (G5, G6: `SELF_ANCESTOR`, `NO_PATH_TO_ROOT`) |

Ghi chú phép thử TREE: lần đầu chỉ dựng lại raw nên view staging trong DB vẫn là bản có lọc vòng, test xanh; phải `dbt run --selector cap_mg_staging` trước. DQ-MOCOI không làm TREE đỏ (DEC-CAP-MG-ORPHAN, phương án D): nhánh mồ côi không có môi giới (G7 → CN9, 23/04 và 24/04) không vào cây; nhánh có môi giới treo vào nút ảo `UNKNOWN` dưới gốc. Cảnh báo vẫn ở `test_stg_regrp_parent_missing`. Tình huống có môi giới không có trong dữ liệu đề, kiểm tay trên `negtest` (chèn tạm raw): TREE xanh 6 ngày, nhánh `G8>G7>UNKNOWN>HO`, sửa cha thì nối về `CN1` từ ngày có bản sửa (bảng ở `ky_thuat_asof_bv.md` AB-06). Sau thay đổi, phép thử âm TREE vẫn đỏ 4. `dv_shape` của `bridge_regrp_ancestor` thêm cột `is_orphan_branch`.

## Gold (`finova-dbt/models/gold/_gold__models.yml`, `finova-dbt/tests/gold/`, tag `gold`; `tests/gold/`)

Phép thử âm chạy trên `cap_mg_phucnd_negtest` bằng script sửa tạm code rồi khôi phục; sau cùng runner full refresh `negtest`. Chi tiết ở `docs/ky_thuat_gold.md` GD-07.

| Mã | Test | Mức | Kiểm gì | Phép thử âm | Kết quả |
|---|---|---|---|---|---|
| Grain (Bảng 24) | `dv_unique_combination` × 5 bảng | error | Không trùng grain của Bảng 71 và Bảng 75 | Bỏ `distinct on (account_hk)` ở tập tiểu khoản của `dim_account_care_daily`, D = 05/05 | Đỏ 200 |
| GT-STG-PII (Gold không có cột định danh) | `dv_shape` × 5 bảng | error | Chỉ có các cột cho phép | Thêm `email_masked` vào `dim_broker_org_daily` | Đỏ 1 cột |
| Tổng khớp vault (Bảng 24) | `test_gold_vault_totals.sql` | error | Số tiểu khoản có phân công = số dòng `bridge_account_broker`; Σ `n_accounts` = số tiểu khoản có `broker_key`; Σ `book_nav` = Σ NAV ngày D qua con trỏ PIT trên satellite raw | `book_nav` bỏ con trỏ PIT, cộng NAV mọi ngày ≤ D, D = 05/05 | Đỏ 2 (ACCOUNTS, BOOKNAV) |
| TC-CAP-MG-ROLLUP | `test_tc_cap_mg_rollup.sql` | error | Tổng chi nhánh (theo `branch_id` của Gold) = tổng các nhóm thuộc chi nhánh theo `bridge_regrp_ancestor` của D; so cả tử, mẫu CAP-MG-COVER30 | Theo đề: dùng cây ngày cuối (15/05) cho D = 29/04 | Đỏ 2 (CN1, CN2: G4 đổi chi nhánh) |
| TC-CAP-MG-RLS | `tests/gold/test_rls.py` (5 test) | pytest | Role `finova_app` với từng người xem trong `org_roles` thấy đúng tập tiểu khoản tính độc lập từ BV và raw, ở mọi ngày; `sec_visibility_daily` chỉ dòng của mình; môi giới thấy ở `dim_broker_org_daily`, `met_broker_daily` đúng phạm vi; không đặt người xem, đặt rỗng hoặc người xem lạ thì không thấy dòng nào; test tự kiểm mỗi người xem có tiểu khoản phải thấy | Theo đề: cho BRK003 xem tiểu khoản của BRK009, D = 11/05 | Đỏ (thừa `9994000001…`); khôi phục xanh |
| D-DQ | `test_gold_dq_recon.sql` | error | Lô LOADED: `rows_landing = rows_valid + rows_rejected`; `rows_landing` = `batch_log.rows_loaded`; mỗi lô có ở đúng một ngày (lô T-GUARD chưa full refresh: tối đa một) | Bỏ dòng `DUPLICATE_EVENT` của `__rejected`, D = 05/05 | Đỏ 1 (lô `CAP-MG-0060`) |
| QT-DAY-REBUILD | grain, PT-FULL | error | Dựng lại ngày D không nhân dòng | Bỏ `asof_day_delete` khỏi pre_hook của Gold, dựng lại 05/05 | Đỏ (24 môi giới, 5 lô trùng) |

### Gold: pytest bổ sung (`tests/gold/test_care_metrics.py`)

Chỉ đọc, chạy trên `CAP_DBNAME`. Phép thử âm ngày 06/11/2026 trên bản sao database bằng chứng, code sửa ở bản clone tạm rồi trả lại.

| Mã | Test | Kiểm gì | Phép thử âm | Kết quả |
|---|---|---|---|---|
| DQ-QUYEN | `test_dq_quyen_not_in_cover30` | Tử COVER30 mọi môi giới, mọi ngày bằng số tính lại từ view as-of bằng Python | Chèn sự kiện giả của BRK009 với `9994000003` ngày 05/05 (trước `FRDATE` 11/05), bỏ `exists` theo ngày được giao, dựng lại 15/05 | Có bộ lọc: 16/22, xanh. Bỏ bộ lọc: 17/22, đỏ |
| DQ-QUYEN | `test_dq_quyen_events_have_no_assignment` | Sự kiện `dq_mg_daily` ghi `EVENT_NOT_ASSIGNED` không có phân công của chính môi giới vào ngày đó | Đổi `key_sample` sang sự kiện hợp lệ | Đỏ |
| TH-NHAPTAY | `test_th_nhaptay_kpi_version_by_cutoff` | Phiên bản chỉ tiêu ngày D là phiên bản mới nhất có `ingested_ts <= cutoff(D)` | `asof_session` đặt cutoff muộn 1 ngày, dựng lại 05/05 | Đỏ: 05/05 ra `CAP-MG-0104` thay vì `CAP-MG-0103` |
| TH-NHAPTAY | `test_th_nhaptay_v2_replaces_v1_target` | Chỉ tiêu trong Gold bằng chỉ tiêu của đúng phiên bản; có môi giới đổi số giữa hai bản | Tăng `kpi_target_calls` của BRK003 ngày 15/05 thêm 1 | Đỏ: 441 khác 440 |
| DQ-CHUADUYET, DQ-CONGTHUC | `test_th_nhaptay_rejected_rows_have_no_target` | Môi giới có dòng bị loại không có chỉ tiêu ở mọi ngày | Đặt chỉ tiêu cho BRK012 ngày 15/05 | Đỏ |
| TH-NGHIVIEC | `test_th_nghiviec_flag_follows_work_status` | `is_carer_inactive` và `DEC-CAP-MG-GAP` trong `care_basis` khớp `work_status` | Tình huống giả: giữ 13 tiểu khoản ở BRK017 tới 05/05, dựng lại 05/05: 13 dòng có cờ, xanh. Bỏ cờ ở `dim_account_care_daily` | Đỏ tại `9994000113` |
| TH-NGHIVIEC | `test_th_nghiviec_accounts_move_to_successor` | 13 tiểu khoản của BRK017 ngày 29/04 đều thuộc BRK018 ngày 04/05 | Đổi một dòng ngày 04/05 sang BRK019 | Đỏ |
| DEC-CAP-MG-BROKERKEY | `test_dec_brokerkey_new_holder_has_no_old_interactions` | Người mang mã BRK017 từ 11/05 có 0 tiểu khoản, BOOKNAV 0, 0 tương tác; người cũ có tương tác | Bỏ lọc `[join_date, leave_date]` ở `met_broker_daily`, dựng lại 12/05 | Đỏ: 16 tương tác |

Dữ liệu đề không đủ để thử hai quy tắc này: điều kiện "vào ngày đang được giao" không đổi tử của môi giới nào, và không tiểu khoản nào mang cờ `is_carer_inactive`. Nếu chỉ sửa code thì test vẫn xanh, nên hai phép thử trên phải thêm dữ liệu giả.

Câu hỏi kiểm (Bảng 74): 8 file SQL ở `evidence/probes/`, `python -m runner.probes` ghi `evidence/probes.csv` (11 dòng).

## Đầu cuối (`tests/e2e/test_e2e.py`)

| Mã | Test | Kiểm gì | Phép thử âm (`negtest`, sửa dữ liệu rồi trả lại) | Kết quả |
|---|---|---|---|---|
| TC-CAP-E2E | `test_tc_cap_e2e_assignment_lineage` | Mọi tiểu khoản có phân công ở `dim_account_care_daily`, mọi ngày: lần được qua `bridge_account_broker` → `asof.esat_reaflnk__flex` (GUC của D) → `sat_reaflnk__flex` (cùng `ingested_ts`, `hash_diff`) → `stg_flex__reaflnk` → đúng dòng `landing.flex_reaflnk` (AUTOID, REACCTNO, AFACCTNO khớp); báo mắt xích đứt theo tầng | Đổi AUTOID một dòng `landing.flex_reaflnk` (lô `CAP-MG-0003`) | Đỏ: `9994000005` đứt ở RAW->STAGING mọi ngày |
| TC-CAP-E2E | `test_tc_cap_e2e_booknav_from_landing` | CAP-MG-BOOKNAV mỗi môi giới, mỗi ngày = Σ NAV lần ngược từ PIT qua raw, `stg_flex__nav` tới dòng `landing.ref_nav` | Đổi NAV ở `landing.ref_nav` của `9994000001` ngày 05/05 (staging ra NAV, hashdiff mới nên chuỗi đứt) | Đỏ: BRK003 ngày 05/05 lệch đúng NAV tiểu khoản đó. Lần đầu sửa NAV ở raw thì xanh suông: `hash_diff` không đổi và Gold đã dựng từ trước, nên hai vế cùng không bị tác động |

## Kết quả lần chạy gần nhất (máy thật, 06/11/2026, bản clone sạch)

Chạy trên bản clone sạch của nhánh, database mới `cap_mg_phucnd_verify`, Python của `.venv` cùng `uv.lock`.

- `runner.init_db`, `runner.run`: 19 lần chạy SUCCESS, khoảng 6 phút rưỡi. `runner.probes`: `evidence/probes.csv` trùng từng dòng với bản đã commit.
- `RUN_PT_FULL=1 pytest -q tests`: 50 passed, 15 phút 46 giây, gồm PT-FULL, PT-IDEMP, T-GUARD.
- 11 test thêm ngày 06/11 (`tests/gold/test_care_metrics.py` 8, `tests/staging/test_reject_rules.py` 3): 11 passed trên database dựng mới. Tổng 61 test.
- D-DBT: `dbt build --selector cap_mg_all` trên database mới, landing đã nạp, schema dbt trống, D = 15/05: PASS 291, WARN 2 (DQ-MOCOI, GT-HUB-NOMASTER), ERROR 0; `dbt test --select test_type:unit`: 11 PASS.
- `dbt build --selector cap_mg_staging`: PASS 75, WARN 1, ERROR 0. `dbt test --selector cap_mg_raw`: PASS 170, WARN 1, ERROR 0.
- `check_khung.py --repo . --de MG --dbt --dbt-cmd 'uv run python -c "from dbt.cli.main import cli; cli()"'`: 22 ĐẠT, 0 KHÔNG ĐẠT, 0 BỎ QUA.
- Bản clone đặt ở thư mục quá sâu thì `runner.run` lỗi `ModuleNotFoundError` do giới hạn 260 ký tự của Windows; xem `README.md`.

## Kết quả lần chạy trước (máy thật, 04/11/2026, có Gold)

- `runner.run --full-refresh --skip-load` trên `cap_mg_phucnd`: SUCCESS, khoảng 2 phút 45 giây (raw một cửa sổ, view as-of, BV và Gold 19 ngày); mỗi ngày `cap_mg_bv` PASS 13, `cap_mg_gold` PASS 20, ERROR 0.
- `RUN_PT_FULL=1 pytest -q tests`: 50 passed, 14 phút 50 giây (17 loader gồm `ingested_ts` bằng `commit_ts`, 1 TC-NEN-HASH-TZ, 13 raw vault gồm PT-FULL so cả 5 bảng Gold, GT-BV-REBUILD, TC-CAP-MG-BACKDATE, 12 as-of, 5 TC-CAP-MG-RLS, 2 TC-CAP-E2E).
- D-DBT: `dbt build --selector cap_mg_all` trên database mới (landing đã nạp, schema dbt trống), D = 15/05: PASS 291, WARN 2 (DQ-MOCOI, GT-HUB-NOMASTER), ERROR 0; sau đó `dbt test --select test_type:unit`: 11 PASS.
- D-RUNBOOK: trên database mới, `runner.init_db` rồi `runner.run` cho 19 lần chạy SUCCESS trong 6 phút 24 giây; `runner.probes` ra đúng `evidence/probes.csv` như DB chính.
- D-BANGCHUNG (`runner.evidence`, database `_evidence`): 59 bảng, view của landing, staging, atomic, asof, mart; chạy lại 15/05 và full refresh khớp lần chạy theo ngày ở mọi bảng (số dòng và md5), lệch 0. Tổng dòng mỗi tầng: landing 5.959, staging 6.027, atomic 14.090, asof (cutoff 15/05) 5.157, mart 7.342.
- `check_khung.py --repo . --de MG --dbt --dbt-cmd 'uv run python -c "from dbt.cli.main import cli; cli()"'`: 22 ĐẠT, 0 KHÔNG ĐẠT, 0 BỎ QUA. Máy phát triển bị Windows Application Control chặn `.venv/Scripts/dbt.exe` (`os error 4551`) từ chiều 04/11, nên lệnh mặc định `uv run dbt` không chạy (lần chạy với lệnh mặc định: 14 ĐẠT, 1 KHÔNG ĐẠT, 6 BỎ QUA); gọi dbt qua `python` thì cùng dbt-core 1.12.5, dbt-postgres 1.11.0.

## Kết quả lần chạy trước (máy thật, 03/11/2026, đến Business Vault)

- `runner.run --full-refresh --skip-load` trên `cap_mg_phucnd`: SUCCESS, 1 phút 25 giây (raw một cửa sổ, view as-of, BV 19 ngày); mỗi lần `cap_mg_bv`: PASS 13, ERROR 0.
- `RUN_PT_FULL=1 pytest -q tests`: 42 passed, 10 phút 41 giây.
- `check_khung.py --repo . --de MG --dbt`: 22 ĐẠT sau khi sửa câu chữ docstring `loader/error_log.py` bị KHUNG-BIMAT nhận nhầm là mật khẩu.

## Kết quả lần chạy trước (máy thật, 03/11/2026, trước khi có as-of và BV)

- `dbt build --selector cap_mg_staging`: PASS 71, WARN 1 (DQ-MOCOI), ERROR 0.
- `dbt build --selector cap_mg_raw` (full refresh, cửa sổ `(-infinity, 15/05]`): PASS 178, WARN 1 (GT-HUB-NOMASTER: CN9), ERROR 0.
- `dbt test --select test_type:unit`: 9 PASS.
- `RUN_PT_FULL=1 pytest -q tests`: 29 passed (16 loader, 1 TC-NEN-HASH-TZ, 12 raw vault), 5 phút 45 giây. Runner trên DB thử:
  - 19 lần chạy theo ngày SUCCESS (17/04 → 15/05);
  - 2 full refresh SUCCESS;
  - 3 `BLOCKED_BY_GUARD` của kịch bản T-GUARD, xử lý bằng 1 FULL_REFRESH và 1 ACCEPTED;
  - `reject_count`: 39 dòng bị loại ở 13 (lô, view, reason_code).
- DB thật `cap_mg_phucnd` sau `--recheck-dup` và full refresh: `pytest -q tests` 22 passed, 7 skipped (chỉ chạy trên DB thử); landing và atomic giống DB thử ở 25 bảng.
- `tools/check_khung.py --de MG --dbt`: 22 ĐẠT, 0 KHÔNG ĐẠT. `tools/check_ctrl.py` trên DB thật (có thêm bảng của `ctrl_runner.sql`): 7 đạt, 0 không đạt.
