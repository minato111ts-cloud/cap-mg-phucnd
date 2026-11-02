# Ma trận test — CAP-MG (D-TEST)

- **Cập nhật:** 02/11/2026, nhánh `feat/cap-mg-phucnd`
- **Phạm vi:** loader (landing, ctrl) và staging. Raw vault trở đi bổ sung khi có model.
- **Cách chạy:** `uv run --env-file .env dbt build --selector cap_mg_staging --project-dir finova-dbt --profiles-dir finova-dbt` và `uv run --env-file .env pytest -q`.
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
| `test_tc_cap_ldz_04_schema_drift_resilience` | Cột mới → thêm cột NULL, ghi `ctrl.schema_drift` |
| `test_tc_cap_ldz_05_inv_t1_load_reject_missing_event_ts` | Dòng không tính được `event_ts` → `ctrl.load_reject` (INV-T1) |
| `test_tc_cap_ldz_06_spreadsheet_physical_tracing` | Dấu vết dòng/cột Excel (`excel_row_no`, `source_col_map`) |
| `test_tc_cap_ldz_07_contract_driven_mock_contract` | Loader chạy theo hợp đồng giả, không ghi cứng tên bảng |
| `test_tc_cap_mg_excel_real_file_headers` / `..._negative_single_header_row` | TC-CAP-MG-EXCEL: tiêu đề hai dòng của file thật; phép thử âm một dòng tiêu đề |
| `test_event_ts_future_guard_uses_threshold` | Quy tắc `event_ts` tương lai đọc ngưỡng từ `thresholds.yaml` |
| `test_thresholds_in_sync_with_dbt_vars` | INV-M6: ngưỡng ở `dbt_project.yml` bằng `thresholds.yaml` |

## Kết quả lần chạy gần nhất (máy thật, 02/11/2026)

- `dbt build --selector cap_mg_staging`: PASS 69, WARN 1 (DQ-MOCOI), ERROR 0.
- `pytest -q`: 15 passed.
