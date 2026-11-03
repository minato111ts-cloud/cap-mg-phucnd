# Ma trận test — CAP-MG (D-TEST)

- **Cập nhật:** 02/11/2026, nhánh `feat/cap-mg-phucnd`
- **Phạm vi:** loader (landing, ctrl), staging và raw vault. Business Vault trở đi bổ sung khi có model.
- **Cách chạy:** `uv run --env-file .env dbt build --selector cap_mg_staging --project-dir finova-dbt --profiles-dir finova-dbt` và `uv run --env-file .env pytest -q`. Raw vault: `python -m runner.run`, `dbt test --select test_type:unit`, và `RUN_PT_FULL=1 pytest -q tests/raw` (xem phần raw vault).
- **Phép thử âm:** cố ý làm hỏng code hoặc dữ liệu để chứng minh test đỏ, rồi khôi phục. Phép thử cần sửa dữ liệu chạy trên bản sao `cap_mg_phucnd_negtest`, không đụng database thật. Cột "Nơi chạy" ghi *máy thật* (PostgreSQL 16 cục bộ, `uv run dbt`) hoặc *thay thế* (môi trường mô phỏng trước 02/11/2026, xem `docs/ky_thuat_landing_staging.md`).

## Staging: test singular (`finova-dbt/tests/staging/`)

| Mã | File | Mức | Kiểm gì | Phép thử âm | Kết quả | Nơi chạy |
|---|---|---|---|---|---|---|
| GT-STG-RECON | `test_stg_reconciliation.sql` | error | Theo từng lô: `batch_log.rows_loaded` = dòng landing = hợp lệ + bị loại | Thêm `and source_row_no <> 1` vào `stg_flex__broker` | Đỏ 3 lô | thay thế |
| GT-STG-KEYTS | `test_stg_keyts.sql` | error | Không có hai dòng hợp lệ cùng (khóa, `ingested_ts`) khác hashdiff | Chèn lô `CAP-MG-9999` cùng `ingested_ts` với `CAP-MG-0002`, BRK001 khác email; gom xung đột theo `batch_id` | Đỏ 1 khóa | máy thật |
| GT-STG-UNIQUE | `test_stg_dedup.sql` (`DUP_KEPT_TWICE`) | error | Mỗi (`ingested_ts`, khóa) tối đa một dòng hợp lệ | Xóa nhánh `_dup_rank > 1` ở `stg_finova_app__events` | Đỏ 12 khóa (`CAP-MG-0060`); KEYTS, RECON xanh | máy thật |
| GT-STG-UNIQUE | `test_stg_dedup.sql` (`DUP_NOT_IDENTICAL`) | error | Dòng loại vì trùng phải cùng hashdiff với dòng được giữ | Chèn BRK001 khác email cùng lô; xóa nhánh `_has_conflict` ở `stg_flex__broker` | Đỏ 1; KEYTS xanh | máy thật |
| GT-STG-PII | `test_stg_pii.sql` | error | Cột định danh không ra staging ở dạng rõ | Bỏ che `mobile_masked` | Đỏ 72 dòng | thay thế |
| TC-CAP-MG-EVENTTIME | `test_stg_events_event_time.sql` | error | Giờ thiết bị lệch tương lai quá ngưỡng thì dùng `server_ts` và có cờ; staging khớp landing | Ngưỡng 10 ngày qua `--vars` | Đỏ 6 dòng | thay thế |
| TC-CAP-MG-EXCEL | `test_stg_kpi_excel.sql` | error | KPI là số; ô lỗi công thức vào `FORMULA_ERROR`; dòng chưa duyệt bị loại | Đọc Excel với `header_rows: 1` | Pytest âm đạt | thay thế |
| DEC-CAP-MG-BROKERKEY | `test_stg_broker_hk_consistent.sql` | error | Cùng mã môi giới cùng `broker_hk` ở 4 nguồn | Reaflnk băm mã không có `'FLEX'` | Đỏ 1306 dòng | thay thế |
| DQ-VONG | `test_stg_regrp_no_cycle.sql` | error | Cây hợp lệ không có vòng mọi độ dài | Bỏ nhánh `CYCLE_DETECTED` | Đỏ 2 nút (G5, G6) | thay thế |
| GT-NHL-CONTENT | `test_stg_nhl_content.sql` | error | Mọi dòng hợp lệ cùng khóa nhl ở mọi lô có cùng nội dung | DB thử: chèn lô gửi lại một `event_id`, đổi `duration_sec` | Đỏ 1 khóa | máy thật |
| DQ-MOCOI | `test_stg_regrp_parent_missing.sql` | warn | Đơn vị trỏ tới cha không có trong bản chụp | Đổi severity sang error | Warn 2 (G7 → CN9) | máy thật |
| null_and_count | `test_stg_attr_nulled.sql` | warn | Ô có giá trị ở landing nhưng NULL ở view hợp lệ (10 cột thuộc tính) | `GRPID = 'X1'`, `raw_event_ts = '20/04/2026 9h'` | Warn 2 ô | máy thật |

## Staging: test cột (`finova-dbt/models/staging/schema.yml`)

- `not_null` (error) trên mọi khóa băm `*_hk`, hashdiff `sat_*_hd`/`nhl_*_hd`, `ingested_ts`, `event_ts`, `is_future_ts_fixed`, `is_device_ts_invalid`, các cột dựng quan hệ (`fr_date`, `to_date`, `tx_date`, `nav`) và `reason_code` của 6 view `__rejected`.
- `not_null` (warn) trên thuộc tính được phép thiếu: `grplevel` (regrp), `join_date`, `grpid` (broker). Phép thử âm của `grpid`: `GRPID = 'X1'` ở DB thử → warn 1 (máy thật).

## Staging: pytest (`tests/staging/`)

| Mã | File | Kiểm gì | Phép thử âm | Kết quả | Nơi chạy |
|---|---|---|---|---|---|
| TC-NEN-HASH-TZ | `test_hash_tz.py` | Mọi cột băm của staging không đổi khi phiên đổi `TimeZone`/`DateStyle` | `dv_fmt_val` dùng `::text` cho timestamptz | Đỏ ở `nhl_broker_event_hd` | thay thế |

## Loader: pytest (`tests/loader/test_loader.py`)

| Test | Kiểm gì |
|---|---|
| `test_tc_cap_ldz_01_spec_invariants_system_columns` | INV-T6: mọi `source_id` có trong `ctrl.source_system` với `is_simulated_ts = true`; INV-T1: 5 cột hệ thống NOT NULL, `record_hash` bytea 32 byte |
| `test_tc_cap_ldz_02_negative_physical_integrity` | File thiếu, sai SHA-256, sai số dòng → `REJECTED_BATCH` |
| `test_tc_cap_ldz_03_idempotency_and_duplicate_content` | Nạp lại → `ALREADY_LOADED`; gửi lặp nội dung → `DUP_CONTENT` |
| `test_tc_cap_ldz_03b_snapshot_revert_is_loaded` | KT-22: bản chụp quay về nội dung cũ (A → B → A) vẫn `LOADED`; chỉ trùng lô gần nhất mới `DUP_CONTENT`. Phép thử âm: so với mọi lô LOADED → đỏ (máy thật) |
| `test_tc_cap_ldz_03c_recheck_dup_reloads_wrongly_skipped` | `--recheck-dup` (KT-22): lô từng bị DUP_CONTENT mà khác lô LOADED liền trước (theo `arrival_seq`) được nạp; vẫn trùng thì giữ nguyên, không ghi thêm sổ; chạy lại không đổi gì. Phép thử âm: bỏ nhánh "vẫn trùng thì không ghi sổ" → đỏ (máy thật) |
| `test_tc_cap_ldz_04_schema_drift_resilience` | Cột mới → thêm cột NULL, ghi `ctrl.schema_drift` |
| `test_tc_cap_ldz_05_inv_t1_load_reject_missing_event_ts` | Dòng không tính được `event_ts` → `ctrl.load_reject` (INV-T1) |
| `test_tc_cap_ldz_06_spreadsheet_physical_tracing` | Dấu vết dòng/cột Excel (`excel_row_no`, `source_col_map`) |
| `test_tc_cap_ldz_07_contract_driven_mock_contract` | Loader chạy theo hợp đồng giả, không ghi cứng tên bảng |
| `test_tc_cap_mg_excel_real_file_headers` / `..._negative_single_header_row` | TC-CAP-MG-EXCEL: tiêu đề hai dòng của file thật; phép thử âm một dòng tiêu đề |
| `test_event_ts_future_guard_uses_threshold` | Quy tắc `event_ts` tương lai đọc ngưỡng từ `thresholds.yaml` |
| `test_thresholds_in_sync_with_dbt_vars` | INV-M6: ngưỡng ở `dbt_project.yml` bằng `thresholds.yaml` |

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

## Raw vault: test singular (`finova-dbt/tests/raw/`, tag `dv_raw`)

| Mã | File | Mức | Kiểm gì | Phép thử âm | Kết quả | Nơi chạy |
|---|---|---|---|---|---|---|
| GT-HUB-UNIQ | (test cột) | error | Hub không trùng khóa | Bỏ `not exists` ở `dv_load_hub`, chạy incremental `hub_broker` cửa sổ `(-infinity, hi]` | Đỏ 24 khóa (`unique`, `bkcc+bk`) | máy thật |
| GT-HUB-NOMASTER | `test_raw_hub_nomaster.sql` | warn | Khóa hub chưa có satellite của nguồn chủ (broker, regrp, reaflnk) | — (test đếm) | Warn 1 (CN9, khớp DQ-MOCOI) | máy thật |
| GT-ESAT-ONEACTIVE | `test_raw_esat_oneactive.sql` | error | Tại mọi thời điểm ghi, mỗi driving key tối đa một link hiệu lực | Bỏ nhánh đóng link cũ ở `dv_load_esat_dk`, build full refresh | Đỏ 1 (G4 từ `CAP-MG-0051`) | máy thật |
| GT-STS-ENUM | `test_raw_sts_transitions.sql` | error | Hai dòng sts liền nhau khác trạng thái; dòng đầu không phải ACTIVE | Bỏ so trạng thái trước ở `dv_load_sts_snapshot` | Đỏ 75 dòng | máy thật |
| Đủ dòng | `test_raw_completeness.sql` | error | Khóa staging (≤ hi_ts) có trong hub/link/nhl; phiên bản cuối của satellite bằng hashdiff dòng staging cuối | `dv_load_sat` chỉ ghi phiên bản đầu mỗi khóa | Đỏ 4 satellite | máy thật |

Test đủ dòng không bắt lỗi ghi sai `ingested_ts` mà phiên bản cuối vẫn đúng: thử đổi `lag` sang sắp ngược thời gian thì test vẫn xanh. Lỗi loại đó do PT-ABA và PT-FULL bắt.

## Raw vault: dbt unit test (`_raw__unit_tests.yml`)

Chạy bằng `dbt test --select test_type:unit` lúc phát triển. Runner không chạy unit test (RV-08). Phép thử âm sửa `macros/raw/dv_load.sql` rồi khôi phục đúng từng byte (máy thật, 03/11/2026). Fixture khóa băm dạng bytea hex; `expect` chỉ dùng cột text, vì dbt so bytea như object Python.

| Mã | Unit test | Kiểm gì | Phép thử âm | Kết quả |
|---|---|---|---|---|
| PT-ABA | `ut_sat_aba_three_versions` | A → B → A trong một cửa sổ ra 3 phiên bản | Khử trùng theo (khóa, hash_diff), bỏ `ingested_ts` | Đỏ (ra 2 phiên bản) |
| T-SAT | `ut_sat_first_row_compares_with_vault` | Dòng đầu cửa sổ trùng phiên bản trong vault thì không ghi | — | Xanh |
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
| PT-FULL | `test_pt_full_matches_daily` | Runner `--full-refresh` một cửa sổ cho cùng số dòng, md5 như chạy 19 ngày |
| Runner | `test_runner_daily_runs`, `test_runner_no_failed_run` | DB thử: đủ 19 lần chạy theo ngày, đều SUCCESS; mọi DB: không lần nào FAILED hay RUNNING |
| DQ-VONG, sts | `test_sts_regrp_g7_deleted_at_cap_mg_0032` | sts_regrp chỉ có G7 DELETED ở `CAP-MG-0032`; G5/G6 bị loại ở `CAP-MG-0061` không bị xóa giả |
| TH-TAICAUTRUC | `test_esat_regrp_parent_g4_switch` | G4: CN2 mở ở `CAP-MG-0001`; CN2 đóng và CN1 mở ở `CAP-MG-0051` |
| DEC-CAP-MG-CYCLE | `test_cycle_rows_never_reach_vault` | Không phiên bản nào có G5 → G6 hay G6 → G5 |
| DEC-CAP-MG-BROKERKEY | `test_broker_code_reuse_versions` | BRK017: 1 khóa hub, 3 phiên bản hồ sơ (người cũ, nghỉ việc, người mới `BRK017:2026-05-11`) |
| DEC-ELT-REJECT | `test_reject_count_matches_rejected_views` | `ctrl.reject_count` của các lần chạy theo ngày bằng số dòng thật của mọi view `__rejected` theo (lô, view, reason_code), mỗi lô ở đúng một lần; full refresh đếm lại đủ |
| T-GUARD | `test_t_guard_blocks_replayed_batch` | Phép thử âm: chèn lô LOADED mang giờ 22/04 sau lần chạy cuối, thì lần sau ghi `BLOCKED_BY_GUARD`; lô có ở `ctrl.guard_block`; chạy lại vẫn chặn, `v_guard_open` gộp 2 lần chặn; `runner.guard list` in lô và lệnh full refresh |
| T-GUARD | `test_t_guard_full_refresh_resolves_block` | Full refresh SUCCESS ghi `guard_resolution` FULL_REFRESH; lần sau không chặn; 19 bảng không đổi |
| T-GUARD | `test_t_guard_accept_lets_run_continue` | ACCEPTED không có lý do bị từ chối; có lý do thì lần sau SUCCESS |

## Kết quả lần chạy gần nhất (máy thật, 03/11/2026)

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
