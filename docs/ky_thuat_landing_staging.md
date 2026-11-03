# Sổ kỹ thuật tầng Landing và Staging — CAP-MG

- **Đề:** `CAP-MG` (môi giới, đơn vị và chăm sóc), `FNV-CAP-DBT v1.5`
- **Ngày lập:** 02/11/2026
- **Thay thế:** các mục staging trong `docs/bao_cao_chot_ky_thuat_staging.md` (bản 30/10/2026). Các quyết định nghiệp vụ `DEC-CAP-MG-*` vẫn ở `docs/decisions.md` (D-QUYETDINH); file này dẫn chiếu tới đó khi cần.

## Mục đích và cách đọc

Sau lần rà soát landing và staging, có 18 vấn đề cần sửa, từ mức chặn tới mức thấp. Lần chạy trên máy thật (02/11/2026) phát hiện thêm 3 vấn đề (KT-19 đến KT-21); khi dựng raw vault phát hiện thêm KT-22. Tất cả được ghi ở một file để khi review hay viva chỉ cần mở một chỗ. Mỗi mục `KT-xx` gồm năm phần:

1. **Vấn đề**: sai ở đâu, file nào.
2. **Lỗi xảy ra thế nào**: cơ chế, kèm hậu quả lên số liệu.
3. **Khắc phục**: đã sửa gì.
4. **Vì sao chọn**: các phương án đã cân nhắc và lý do chọn.
5. **Bằng chứng**: lệnh hoặc test đã chạy và kết quả.

## Môi trường kiểm chứng

**Máy thật (02/11/2026).** Smart App Control chặn `python.exe` không ký số của bản Python do uv tải về. Đã chuyển `.venv` sang Python 3.12 bản python.org (có chữ ký PSF) và đặt `python-preference = "only-system"` trong `pyproject.toml`. Trên PostgreSQL 16 cục bộ (service Windows, cổng 5432), database `cap_mg_phucnd` dựng mới:

- Loader nạp 104/104 lô: 61 `LOADED` (5.939 dòng), 43 `SKIPPED_DUP/DUP_CONTENT` (3.322 dòng); tổng 9.261 dòng, bằng tổng `row_count` của manifest. `load_reject` và `schema_drift` rỗng. Sau KT-22: 63 `LOADED` (5.959 dòng), 41 `SKIPPED_DUP` (3.302 dòng).
- `uv run dbt build --selector cap_mg_staging`: PASS 69, WARN 1 (DQ-MOCOI, G7 → CN9), ERROR 0.
- `uv run pytest`: 15 passed.
- Phép thử âm cần sửa dữ liệu chạy trên bản sao `cap_mg_phucnd_negtest` (pg_dump/pg_restore), không đụng database thật.

**Môi trường thay thế (trước 02/11/2026).** Khi máy thật chưa chạy được `uv run dbt`, việc kiểm chứng làm trên môi trường thay thế, dùng dữ liệu thật của gói đề:

- PostgreSQL 16.15 cục bộ, database `cap_mg_test` dựng từ đầu bằng `setup/bootstrap.sql` và `setup/ctrl.sql` của repo.
- Loader thật (`python -m loader.load`) nạp toàn bộ 104 lô của manifest.
- Model staging render bằng **chính macro của project** qua Jinja2 (thay `dbt`), tạo view với role `finova_dbt`, rồi chạy mọi test singular và test `not_null`.
- `pytest tests/` chạy trên cùng database.
- `tools/check_khung.py --de MG` mức tĩnh: **14 ĐẠT, 0 KHÔNG ĐẠT**.

Các phép thử âm trong bảng KT-07 đánh dấu "môi trường thay thế" chưa chạy lại trên máy thật.

## Bảng tổng hợp

| Mã | Mức | Vấn đề | Trạng thái |
|---|---|---|---|
| KT-01 | Chặn | Tiêu đề Excel tiếng Việt không ánh xạ được, KPI ở landing toàn NULL | Đã sửa, có test |
| KT-02 | Chặn | `broker_hk` tính khác nhau giữa các staging | Đã sửa (DEC-CAP-MG-BROKERKEY PA A), có test |
| KT-03 | Cao | Staging lọc cửa sổ `(lo, hi]`; khử trùng giữ bản mới nhất | Đã sửa |
| KT-04 | Cao | `event_ts` landing ≠ staging; ngưỡng 5 phút ghi cứng | Đã sửa, có test |
| KT-05 | Cao | `ref/` nạp vào landing bằng TRUNCATE, thiếu cột kỹ thuật | Đã sửa (seed) |
| KT-06 | Cao | GT-STG-RECON so theo bảng, không theo lô | Đã sửa |
| KT-07 | Trung bình | Thiếu test bắt buộc và phép thử âm | Đã bổ sung 8 test, 6 phép thử âm |
| KT-08 | Trung bình | PII ra staging ở dạng rõ | Đã sửa, có test |
| KT-09 | Trung bình | `__rejected` khác cột; logic phân loại chép đôi | Đã sửa |
| KT-10 | Trung bình | Ép kiểu không kiểm, một ô sai làm sập cả view | Đã sửa, kiểm 20 ca biên |
| KT-11 | Trung bình | Dò vòng cây chỉ bắt vòng 2 nút | Đã sửa, có test |
| KT-12 | Trung bình | `batch_log` không ghi lần nạp lại; sai mã `FILE_MISSING`; thiếu rollback | Đã sửa, có test |
| KT-13 | Trung bình | Cổng mặc định 5432, đề quy định 5436 | Đã sửa |
| KT-14 | Thấp | Thiếu `bkcc`; hub giả `nav_hk`, `kpi_hk`; tên hashdiff | Đã sửa |
| KT-15 | Thấp | Luật mềm `is_active` ở staging | Đã bỏ |
| KT-16 | Thấp | `event_date` phụ thuộc TimeZone của phiên | Đã sửa |
| KT-17 | Thấp | Chưa cài CONFLICT_IN_BATCH và khử dòng lặp cho bản chụp | Đã sửa |
| KT-18 | Thấp | Cột thuộc tính hỏng làm loại cả dòng | Đã sửa |
| KT-19 | Cao | Xung đột giữa hai lô cùng `ingested_ts` lọt qua staging (GT-STG-KEYTS đỏ) | Đã sửa, có phép thử âm |
| KT-20 | Trung bình | Không test nào bắt khử trùng hỏng; phép thử âm KEYTS ghi sai | Đã bổ sung test, có phép thử âm |
| KT-21 | Thấp | Cột có mẫu `null_and_count` không kiểm mẫu; giờ thiết bị sai bị thay âm thầm | Đã sửa, có test warn |
| KT-22 | Cao | `DUP_CONTENT` bỏ qua bản chụp quay về nội dung cũ (A → B → A) | Đã sửa, có test |

**Số dòng staging trước và sau refactor** (cùng landing, 104 lô): không đổi ở cả 12 view. Như vậy refactor không làm đổi kết quả trên dữ liệu đề, và lý do loại khớp từng lỗi đã ghi ở D-KHAOSAT.

| View | Hợp lệ | Bị loại | Lý do loại |
|---|---|---|---|
| `stg_finova_app__events` | 634 | 19 | 12 `DUPLICATE_EVENT`, 4 `KEY_NULL`, 3 `ALLCODE_UNKNOWN` (VIDEO) |
| `stg_flex__broker` | 72 | 0 | — |
| `stg_flex__reaflnk` | 1306 | 10 | 10 `INVALID_DATE_RANGE` (AUTOID 201, 202 × 5 lô) |
| `stg_flex__regrp` | 50 | 2 | 2 `CYCLE_DETECTED` (G5, G6 ở CAP-MG-0061) |
| `stg_manual__kpi` | 38 | 8 | 6 `UNAPPROVED_ROW`, 2 `FORMULA_ERROR` |
| `stg_ref__nav` | 3800 | 0 | — |

---

## KT-01 (Chặn): Tiêu đề Excel tiếng Việt không ánh xạ được

**Vấn đề.** `loader/load.py` (`resolve_excel_column_name`) ánh xạ tiêu đề Excel sang tên cột hợp đồng bằng cách so tên đã chuẩn hóa, hoặc so `aliases`. `contracts/manual_kpi.yml` không khai `aliases`.

**Lỗi xảy ra thế nào.** File thật có tiêu đề hai dòng tiếng Việt (gộp ô `C1:E1`). Bước ghép tiêu đề đúng, ra "Mã môi giới", "Số cuộc gọi"… Nhưng `normalize_token("Mã môi giới")` cho `ma_moi_gioi` ≠ `broker_id`, nên không cột nào khớp. Loader lấy giá trị theo tên cột hợp đồng (`row_dict.get("broker_id")`), nên **mọi cột ra NULL**. Cùng lúc, 7 tiêu đề tiếng Việt bị coi là cột mới: chạy `ALTER TABLE` và ghi vào `ctrl.schema_drift`. Lô vẫn mang trạng thái `LOADED`. Staging xếp cả 46 dòng vào `__rejected` (`KEY_NULL`), view hợp lệ có 0 dòng.

**Vì sao `dbt build` vẫn xanh.** Test `not_null` trên view rỗng luôn đạt. GT-STG-RECON vẫn cân (46 = 0 + 46). Test TC-CAP-LDZ-06 tự sinh file Excel có tiêu đề **chính là** tên cột hợp đồng, nên không bao giờ gặp tiêu đề thật.

**Khắc phục.**
- Thêm `aliases` cho cả 7 cột trong `contracts/manual_kpi.yml`.
- Loader gắn cờ `CONTRACT_COLUMN_MISSING`, kèm danh sách cột thiếu ở `detail`, khi file thiếu cột của hợp đồng.
- Thêm test đọc **file thật** của gói đề (`test_tc_cap_mg_excel_real_file_headers`) và phép thử âm đọc với `header_rows: 1`.
- Thêm `tests/staging/test_stg_kpi_excel.sql`.

**Vì sao chọn.** Khai `aliases` trong hợp đồng giữ đúng nguyên tắc "loader đọc theo hợp đồng, không ghi cứng tên cột". Phương án đổi tên cột trong file nguồn bị loại, vì landing phải giữ nguyên văn nguồn. Cờ `CONTRACT_COLUMN_MISSING` được thêm vì đây là lỗi im lặng: lô vẫn `LOADED`, chỉ dữ liệu sai. Có cờ thì lỗi cùng loại lộ ngay ở sổ nạp, trước khi xuống staging.

**Bằng chứng.**
- Trước sửa: 0/7 tiêu đề ánh xạ được. Sau sửa: 7/7.
- Landing có `broker_id = BRK001`, `target_aum_bil = '10,5'`; `ctrl.schema_drift` rỗng.
- Staging: 38 dòng hợp lệ và 8 bị loại, đúng D-KHAOSAT (mỗi file 3 dòng chưa duyệt, 1 dòng `#REF!`).

## KT-02 (Chặn): `broker_hk` tính khác nhau giữa các staging

**Vấn đề.** `stg_flex__broker` băm `(BROKERID, JOINDATE)`, còn `stg_flex__reaflnk`, `stg_finova_app__events`, `stg_manual__kpi` băm `BROKERID`.

**Lỗi xảy ra thế nào.** Link phân công và link sự kiện sẽ trỏ tới khóa không có trong hub (GT-LNK-PARENT đỏ ở raw vault). Ở staging không test nào so `broker_hk` giữa các view, nên lỗi không lộ.

**Khắc phục.**
- Mọi staging mang mã môi giới dùng `broker_hk = dv_hash('FLEX', broker_id)`, kèm hai cột `bkcc_broker`, `bk_broker`.
- `join_date` vào hashdiff `sat_broker_profile_hd`. `broker_key = BROKERID:JOINDATE` giữ lại làm thuộc tính để Business Vault tách người.
- Hợp đồng `flex_broker`: `business_key: [BROKERID]`.
- Test mới `test_stg_broker_hk_consistent.sql`.

**Vì sao chọn.** Xem đầy đủ ở `docs/decisions.md` mục `DEC-CAP-MG-BROKERKEY`. Tóm tắt:
- Sự kiện app và KPI không phải nguồn FLEX, nên staging không được tra JOINDATE (Q19). Dù chọn phương án nào, logic khoảng làm việc vẫn phải nằm ở Business Vault.
- Khóa ghép còn vướng 4 phân công có FRDATE trước JOINDATE, và cả 4 đều là BRK017.
- PA A đặt logic tách người ở đúng một chỗ.
- Đã sửa luôn số liệu sai trong sổ cũ ("17 sự kiện", "2 và 4 tương tác"). Số đúng: 16 sự kiện, đều trong 20–29/04; người mới mang mã từ 11/05 có 0 tương tác.

**Bằng chứng.** Test xanh. Phép thử âm (reaflnk băm mã không có `'FLEX'`) đỏ 1306 dòng.

## KT-03 (Cao): Staging lọc cửa sổ nạp; khử trùng giữ bản mới nhất

**Vấn đề.** Mọi view staging có `where {{ dv_window('ingested_ts') }}`. Khử trùng sự kiện gom theo `event_id` trên cả cửa sổ và giữ `ingested_ts` **mới nhất**.

**Lỗi xảy ra thế nào.**
- Đề đặt cửa sổ `(lo, hi]` ở model vault (E.5: "Model vault chỉ đọc dòng staging có lo_ts < ingested_ts ≤ hi_ts"). Đặt ở staging làm kết quả staging phụ thuộc cửa sổ.
- Chạy theo ngày thì mỗi cửa sổ một lô. Full refresh (`lo = -infinity`) thì mọi lô chung một cửa sổ. Một `event_id` gửi ở hai lô sẽ bị khử ở full refresh nhưng không bị khử khi chạy theo ngày, và lại giữ bản **muộn hơn**, trái INV-T3 ("giữ ingested_ts của lần đầu"). Kết quả là rủi ro trượt cổng PT-FULL.
- GT-STG-RECON và báo cáo chất lượng chỉ thấy lô trong cửa sổ; staging cũng không truy vấn được nếu không truyền biến.

**Khắc phục.**
- Bỏ `dv_window` khỏi mọi staging.
- Khử trùng và phát hiện xung đột chỉ trong **một lô** (`partition by batch_id, khóa`), giữ dòng đầu theo `source_row_no` (macro `stg_batch_dup_cols`). *Đã nới thành một lần thấy (`partition by ingested_ts, khóa`) ở KT-19.*
- Trùng giữa các lô để raw vault xử lý (hub/nhl chỉ chèn khóa chưa có, nên tự giữ lần thấy đầu).

**Vì sao chọn.**
- Staging là view, không lưu gì, nên lọc cửa sổ ở đây không tiết kiệm được gì; chi phí theo cỡ lô đến từ việc model incremental của vault lọc.
- Khử trong một lô cho cùng kết quả dù chạy theo ngày hay full refresh, vì mỗi lô luôn được xét trọn vẹn.
- Phương án "giữ cửa sổ ở staging nhưng khử theo lô" bị loại: vẫn làm staging phụ thuộc biến và giới hạn GT-STG-RECON.

**Hệ quả cho tầng sau.** Model raw vault **phải** tự gọi `{{ dv_window() }}` khi đọc staging.

**Bằng chứng.** `dbt build --selector cap_mg_staging` giờ không cần `--vars`. Số dòng không đổi so với trước (bảng ở đầu file).

## KT-04 (Cao): `event_ts` landing ≠ staging; ngưỡng ghi cứng

**Vấn đề.**
- Hợp đồng ghi `event_ts.expr` là một câu SQL `case`. Loader không thực thi câu đó mà dò chuỗi tìm tên cột, nên landing lấy luôn giờ thiết bị.
- Staging tự sửa lại DQ-TUONGLAI với `interval '5 minutes'` ghi cứng.

**Lỗi xảy ra thế nào.** 6 sự kiện của lô CAP-MG-0036 có `landing.event_ts` là giờ thiết bị (30/04), trong khi staging dùng `server_ts` (27/04). Hai tầng mang hai giá trị khác nhau cho cùng một cột kỹ thuật. Ngưỡng ghi cứng vi phạm INV-M6, và không làm được phép thử âm của TC-CAP-MG-EVENTTIME ("đặt ngưỡng 10 ngày").

**Khắc phục.**
- Hợp đồng `finova_app_events` thêm trường máy đọc: `column: event_ts`, `fallback_columns: [server_ts]`, `future_guard: {compare_to: server_ts, tolerance_minutes_key: event_future_tolerance_minutes}`.
- Loader thực thi đúng các trường này. Hợp đồng không khai `column` mà cũng không lấy theo commit_ts thì loader báo lỗi, không đoán nữa.
- Ngưỡng nằm ở `customers/ctcka/thresholds.yaml`. dbt nhận cùng giá trị qua `vars` (`event_future_tolerance_minutes: 5`).
- Staging giữ giờ thiết bị gốc ở cột `device_event_ts` và có cờ `is_future_ts_fixed`.
- Test: `test_stg_events_event_time.sql` (kiểm cả việc staging khớp landing), `test_event_ts_future_guard_uses_threshold`, `test_thresholds_in_sync_with_dbt_vars`.

**Vì sao chọn.**
- dbt không đọc được file YAML ngoài project, nên ngưỡng có hai bản sao: thresholds.yaml cho loader, `vars` cho dbt. Một pytest chặn hai bản lệch nhau.
- Phương án "landing lấy `server_ts`, chỉ staging sửa" bị loại: `event_ts` ở hai tầng vẫn khác nhau cho mọi sự kiện (lệch vài giây), trái INV-T1 (loader tính theo hợp đồng).
- Phương án "chỉ staging dùng `landing.event_ts`" bị loại: TC-CAP-MG-EVENTTIME đặt ở tầng staging và đòi phép thử âm đổi ngưỡng.

**Bằng chứng.**
- Landing: đúng 6 dòng có `event_ts` ≠ giờ thiết bị.
- Test xanh. Phép thử âm với `--vars '{"event_future_tolerance_minutes": 14400}'`: test đỏ 6 dòng (`LANDING_EVENT_TS_MISMATCH`), cờ mất hết.

## KT-05 (Cao): Danh mục `ref/` nạp vào landing bằng TRUNCATE

**Vấn đề.** `ensure_landing_infrastructure` nạp `ref/*.csv` vào `landing.ref_*` bằng `TRUNCATE` rồi `INSERT` mỗi lần chạy.

**Lỗi xảy ra thế nào.**
- Các bảng này thiếu 5 cột kỹ thuật (vi phạm INV-T1: mọi bảng landing có `event_ts`, `ingested_ts` NOT NULL).
- Bị xóa và ghi lại (landing phải chỉ thêm dòng).
- Không đi theo manifest, nên không có trong `batch_log`.

**Khắc phục.**
- Chép ba file vào `finova-dbt/seeds/ref_calendar.csv`, `ref_event_type.csv`, `ref_org_roles.csv` (bỏ BOM, đổi xuống dòng LF).
- Seed có tag `staging`, nên `--selector cap_mg_staging` dựng luôn.
- Staging đọc bằng `ref('ref_event_type')`.
- Bỏ đoạn nạp `ref/` khỏi loader và khỏi `sources.yml`.

**Vì sao chọn.**
- Danh mục tĩnh, nhỏ, đi kèm phiên bản code: đúng chỗ của dbt seed.
- Phương án "nạp `ref/` như một lô landing có 5 cột kỹ thuật" bị loại: các file này không có trong manifest, nên không có `commit_ts` làm `ingested_ts`; tự bịa mốc thời gian sẽ vi phạm INV-T2.

**Bằng chứng.** Sau khi dựng lại, landing không còn bảng `ref_*`. Seed nạp 36, 4, 4 dòng.

## KT-06 (Cao): GT-STG-RECON so theo bảng

**Vấn đề.** Test cũ so tổng số dòng theo bảng, trên cửa sổ.

**Lỗi xảy ra thế nào.**
- Đề yêu cầu so **mỗi `batch_id`** (Bảng 24, Bảng 85). So theo tổng thì lỗi ở hai lô có thể bù trừ nhau.
- D-DQ cần số theo lô (Phụ lục C).
- Test cũ cũng không kiểm sổ nạp.

**Khắc phục.** `tests/staging/test_stg_reconciliation.sql` so theo `(source_table, batch_id)`, đủ ba vế: `ctrl.batch_log.rows_loaded` = số dòng landing = hợp lệ + bị loại. Thêm source `ctrl.batch_log` vào `sources.yml`, thay cho tên bảng ghi cứng.

**Vì sao chọn.** Thêm vế `batch_log` thì cùng một test bắt được cả lỗi loader (sổ ghi lệch landing) lẫn lỗi staging (dòng không vào view nào). Bảng `dq_*` ở Gold sẽ dùng lại đúng cách đếm này.

**Bằng chứng.** Xanh. Phép thử âm (một dòng broker biến mất khỏi view hợp lệ) đỏ ở 3 lô của `flex_broker`.

## KT-07 (Trung bình): Thiếu test bắt buộc và phép thử âm

**Vấn đề.** Staging chỉ có `not_null`/`unique` và một GT-STG-RECON. Đề bắt buộc GT-STG-KEYTS, TC-NEN-HASH-TZ, GT-STG-PII cùng các test riêng của đề, mỗi test kèm phép thử âm (mục 2.6).

**Khắc phục.** Bảng dưới liệt kê test, phép thử âm và kết quả. Dòng không ghi "máy thật" là kết quả trên môi trường thay thế:

| Test | File | Phép thử âm | Kết quả |
|---|---|---|---|
| GT-STG-RECON | `finova-dbt/tests/staging/test_stg_reconciliation.sql` | Thêm `and source_row_no <> 1` vào `stg_flex__broker` | Đỏ 3 lô |
| GT-STG-KEYTS | `test_stg_keyts.sql` | DB thử: chèn lô `CAP-MG-9999` cùng `ingested_ts` với `CAP-MG-0002`, BRK001 khác email; gom xung đột theo `batch_id` | Đỏ 1 khóa (máy thật, KT-19) |
| GT-STG-UNIQUE | `test_stg_dedup.sql` vế `DUP_KEPT_TWICE` | Xóa nhánh `_dup_rank > 1` ở `stg_finova_app__events` | Đỏ 12 khóa ở `CAP-MG-0060`; KEYTS, RECON vẫn xanh (máy thật, KT-20) |
| GT-STG-UNIQUE | `test_stg_dedup.sql` vế `DUP_NOT_IDENTICAL` | DB thử: chèn BRK001 khác email vào cùng lô, xóa nhánh `_has_conflict` ở `stg_flex__broker` | Đỏ 1; KEYTS vẫn xanh (máy thật, KT-20) |
| null_and_count (warn) | `test_stg_attr_nulled.sql` | DB thử: `GRPID = 'X1'`, `raw_event_ts = '20/04/2026 9h'` | Warn 2 ô (máy thật, KT-21) |
| GT-STG-PII | `test_stg_pii.sql` | Bỏ che `mobile_masked` | Đỏ 72 dòng |
| TC-NEN-HASH-TZ | `tests/staging/test_hash_tz.py` (pytest) | `dv_fmt_val` dùng `::text` cho timestamptz | Đỏ ở `nhl_broker_event_hd` của 2 view sự kiện |
| TC-CAP-MG-EVENTTIME | `test_stg_events_event_time.sql` | Ngưỡng 10 ngày qua `--vars` | Đỏ 6 dòng |
| TC-CAP-MG-EXCEL | `test_stg_kpi_excel.sql`, pytest loader | Đọc với `header_rows: 1` | Pytest âm đạt (đọc sai cột như dự kiến) |
| DEC-CAP-MG-BROKERKEY | `test_stg_broker_hk_consistent.sql` | Reaflnk băm mã không có `'FLEX'` | Đỏ 1306 dòng |
| DQ-VONG | `test_stg_regrp_no_cycle.sql` | Bỏ nhánh `CYCLE_DETECTED` | Đỏ 2 nút (G5, G6) |
| DQ-MOCOI (warn) | `test_stg_regrp_parent_missing.sql` | Đổi severity sang error | Warn 2 dòng (G7 → CN9) |

**Vì sao chọn.**
- TC-NEN-HASH-TZ viết bằng pytest, không viết bằng dbt test: dbt test chạy trong một phiên duy nhất nên không đổi TimeZone giữa chừng được. Staging là view nên đọc dưới hai phiên là tính lại hai lần, đúng ý "chạy staging dưới hai thiết lập phiên".
- `test_stg_regrp_no_cycle` dò vòng **độc lập** với macro. Lần thử âm đầu, khi chưa có test này, việc bỏ dò vòng vẫn xanh; nên test này được thêm sau.

## KT-08 (Trung bình): PII ra staging ở dạng rõ

**Vấn đề.** Hợp đồng khai `pii_columns` (FULLNAME, EMAIL, MOBILE của broker; fullname của KPI), nhưng staging và `__rejected` vẫn xuất giá trị rõ.

**Khắc phục.**
- Staging chỉ xuất `email_masked` (`m***@ctcka.example`) và `mobile_masked` (`******5903`, giữ 4 số cuối). Họ tên không xuất.
- Giá trị gốc chỉ đi vào hashdiff (băm một chiều), để đổi số điện thoại vẫn sinh phiên bản mới.

**Vì sao chọn.**
- Gold của đề không cần tên hay số điện thoại (Bảng 71), nên che ở staging là đủ và đơn giản nhất.
- Phương án "tách satellite định danh sang schema riêng" để dành cho khi có yêu cầu xem bản gốc.
- Bỏ PII khỏi hashdiff bị loại: đổi số điện thoại sẽ không sinh phiên bản.

**Bằng chứng.** `test_stg_pii.sql` xanh; phép thử âm đỏ.

## KT-09 (Trung bình): `__rejected` khác cột; logic phân loại chép đôi

**Vấn đề.**
- View hợp lệ và view `__rejected` mỗi bên tự chép nguyên khối `case when` phân loại.
- `__rejected` xuất cột `raw_*` và tên `reject_reason`, trong khi DEC-ELT-REJECT quy định "cùng cột, thêm `reason_code`".

**Lỗi xảy ra thế nào.** Sửa một bên mà quên bên kia thì có dòng rơi vào cả hai view hoặc không vào view nào. GT-STG-RECON chỉ bắt được trường hợp lệch số lượng.

**Khắc phục.**
- Mỗi nguồn có `macros/staging/<model>.sql` gồm hai macro: `<model>_rows()` (phân loại một lần, ra cột `reason_code`) và `<model>_columns()` (danh sách cột chung).
- View hợp lệ lấy `reason_code is null`; view `__rejected` lấy `is not null` và thêm cột `reason_code`.
- Truy về landing bằng `(batch_id, source_row_no)`.

**Vì sao chọn.**
- Không dùng model `ephemeral` dùng chung: checklist của đề không khuyến khích ephemeral.
- Không thêm view trung gian: DEC-ELT-STGVIEW chỉ cho phép hai loại view dẫn xuất ở staging.
- Macro giữ đúng 12 view và đúng một nguồn logic.

## KT-10 (Trung bình): Ép kiểu không kiểm

**Vấn đề.** `::integer`, `::numeric`, `::timestamptz` dùng trực tiếp. `to_date('31/02/2026', 'DD/MM/YYYY')` qua được regex nhưng PostgreSQL báo lỗi.

**Lỗi xảy ra thế nào.** Chỉ một ô sai là truy vấn trên view báo lỗi, staging của **mọi lô** đều hỏng, và runner dừng. Dữ liệu đề hiện chưa có ô như vậy, nhưng DQ-NGAY-SAI, DQ-SO-DINHDANG là nhóm lỗi đề cài được.

**Khắc phục.** `macros/staging/stg_parsers.sql`:
- `stg_parse_date`: kiểm ngày tồn tại trước khi gọi `make_date`.
- `stg_parse_ts`: ISO-8601; có offset thì ép thẳng; thiếu offset thì hiểu là +07:00, cùng quy tắc với loader.
- `stg_parse_number(col, decimal_sep)`: đọc số dạng chữ có dấu phân cách.
- `stg_parse_int`, `stg_is_excel_error`, `stg_code`.
- Cột khóa không đọc được thì loại dòng; cột thuộc tính thì để NULL và đếm (xem KT-18).

**Vì sao chọn.** CASE lồng nhau đảm bảo PostgreSQL chỉ gọi hàm có thể báo lỗi sau khi giá trị đã qua kiểm tra. Hợp đồng khai `decimal_sep` cho từng cột vì '1,500' không tự phân biệt được là 1500 hay 1,5: file Excel nhập tay dùng `,`, file hệ thống dùng `.`.

**Bằng chứng.** 20/20 ca biên đúng: 31/02 và tháng 13 ra NULL, 29/02/2024 hợp lệ, `'1.200,75'` thành 1200.75, `'1,500,000'` thành 1500000, `'#REF!'` ra NULL.

## KT-11 (Trung bình): Dò vòng cây chỉ bắt vòng 2 nút

**Vấn đề.** Logic cũ chỉ bắt A → A và A ↔ B.

**Khắc phục.** CTE đệ quy trên từng lô: đi ngược lên cha từ mỗi nút, quay lại chính nút xuất phát thì nút nằm trên vòng. Giới hạn độ sâu 100 để luôn dừng.

**Vì sao chọn.**
- Dữ liệu đề chỉ có G5 ↔ G6, nhưng TC-CAP-MG-TREE đòi cây không có vòng ở mọi độ dài.
- Dò ở staging là tra trong cùng nguồn, cùng lô (luật cứng hợp lệ). Business Vault giữ phiên bản cây trước theo DEC-CAP-MG-CYCLE.
- Nút không nằm trên vòng nhưng trỏ vào vòng không bị loại; TC-CAP-MG-TREE ở Business Vault kiểm đường lên HO.

**Bằng chứng.** Vẫn loại đúng G5, G6. `test_stg_regrp_no_cycle` có phép thử âm đỏ.

## KT-12 (Trung bình): Sổ `batch_log` khi nạp lại; mã lỗi; rollback

**Vấn đề.**
- Nạp lại `batch_id` đã `LOADED` thì loader trả kết quả mà không ghi sổ.
- Mã lỗi `FILE_NOT_FOUND`, trong khi Bảng 18 là `FILE_MISSING`.
- Lỗi giữa chừng không rollback.

**Khắc phục.**
- Nạp lại thì ghi `SKIPPED_DUP / ALREADY_LOADED`, kèm `loaded_log_id`.
- Đổi sang `FILE_MISSING`.
- Mọi dòng sổ mang `arrival_seq` trong `detail`. `load_manifest_batches` bỏ qua dòng manifest đã có trong sổ.
- Gom 5 câu INSERT giống nhau thành `_log_batch`.
- Rollback cả lô (kể cả `ALTER TABLE` của schema drift) khi có lỗi.

**Vì sao chọn arrival_seq.** Nếu chỉ ghi `ALREADY_LOADED` mỗi lần gặp lô cũ, runner gọi loader mỗi ngày sẽ ghi lặp sổ cho cả 104 lô, tức hơn 2.000 dòng vô nghĩa trong 20 ngày. Lọc theo `arrival_seq` phân biệt được "dòng manifest đã xử lý" với "lô gửi lại" (dòng manifest mới cùng `batch_id`, ứng với TH-GUILAI), và chỉ lô gửi lại mới được ghi `ALREADY_LOADED`/`DUP_CONTENT`.

**Bằng chứng.** Lần chạy thứ hai xử lý 0 lô. Test LDZ-02, LDZ-03 cập nhật và xanh.

## KT-13 (Trung bình): Cổng mặc định 5432

**Vấn đề.** REQ-ENV-07 quy định container `finova-pg16-dev` nghe `127.0.0.1:5436`.

**Khắc phục.** Đổi mặc định ở `.env.example`, `finova-dbt/profiles.example.yml` và loader. ⚠️ Nếu máy bạn đang chạy PostgreSQL ở 5432, đặt `CAP_PGPORT=5432` trong môi trường của mình; đừng sửa mặc định trong repo.

## KT-14 (Thấp): `bkcc`, hub giả, tên hashdiff, record_source

**Khắc phục.**
- Mọi khóa băm hub có `bkcc` theo KAT-TEXT: `FLEX` cho môi giới, tiểu khoản, đơn vị, phân công; `FINOVA_APP` cho sự kiện. Kèm cột `bkcc_<vai>`, `bk_<vai>` (E.5).
- Bỏ `nav_hk` và `kpi_hk`: NAV là satellite theo ngày của tiểu khoản, chỉ tiêu là satellite của môi giới; cả hai không phải khái niệm nghiệp vụ có khóa riêng.
- Đổi tên hashdiff theo `<satellite>_hd`: `sat_broker_profile_hd`, `sat_reaflnk_hd`, `sat_regrp_hd`, `sat_account_nav_hd`, `sat_broker_kpi_hd`, `nhl_broker_event_hd`.
- `record_source` theo dạng `'<nguồn>.<bảng>'`.

**Vì sao chọn.** Thiếu `bkcc` thì một mã trùng nhau giữa hai hệ thống sẽ ra cùng khóa băm. Có thể sửa ngay vì raw vault chưa dựng, nên chưa có dữ liệu phải chuyển đổi.

## KT-15 (Thấp): Luật mềm `is_active` ở staging

**Vấn đề và khắc phục.** "Môi giới còn hoạt động tại ngày D" là phán xét nghiệp vụ, phụ thuộc ngày D và DEC-CAP-MG-GAP, nên là luật mềm (Q19: staging chỉ có luật cứng). Đã bỏ khỏi staging. Business Vault/Gold tính từ `status`, `join_date`, `leave_date` tại D.

## KT-16 (Thấp): `event_date` phụ thuộc TimeZone của phiên

**Vấn đề.** Phát hiện trong lúc refactor: `event_ts::date` lấy ngày theo TimeZone của phiên. Ở phiên UTC, sự kiện lúc 06:30 sáng giờ Việt Nam bị tính sang ngày hôm trước.

**Khắc phục.** Dùng `(event_ts at time zone 'Asia/Ho_Chi_Minh')::date`. Độ phủ 30 ngày (CAP-MG-COVER30) tính theo ngày lịch Việt Nam.

## KT-17 (Thấp): CONFLICT_IN_BATCH và khử dòng lặp cho bản chụp

**Vấn đề.** Hợp đồng khai `CONFLICT_IN_BATCH` nhưng staging bản chụp chưa cài.

**Khắc phục.** Macro `stg_batch_dup_cols` dùng cho cả 6 nguồn:
- Cùng khóa, cùng hashdiff trong một lô: dòng lặp (DQ-TRUNG-NGUYEN, hướng SUA). Giữ dòng đầu, dòng sau vào `__rejected` với `DUPLICATE_ROW`/`DUPLICATE_EVENT`.
- Cùng khóa, khác hashdiff: xung đột (DQ-TRUNG-XUNGDOT). Loại **mọi** dòng của khóa đó.

**Vì sao chọn.** So bằng hashdiff (sau chuẩn hóa), không bằng `record_hash` (nguyên văn). Như vậy hai dòng chỉ khác hoa thường hoặc khoảng trắng là dòng lặp, không bị tính là xung đột. Dòng lặp nằm ở `__rejected` để GT-STG-RECON vẫn cân; D-DQ ghi hướng xử lý là SUA.

## KT-18 (Thấp): Cột thuộc tính hỏng làm loại cả dòng

**Vấn đề.** Staging cũ loại dòng môi giới khi thiếu GRPID; hợp đồng regrp đặt `reject` cho GRPNAME, GRPLEVEL.

**Khắc phục.**
- Chỉ loại trong bốn trường hợp của mục 2.5: không dựng được khóa, sai mẫu khóa, mã danh mục lạ, xung đột trong lô.
- Cộng thêm các luật đề nêu riêng: ngày phân công sai (DQ-NGAY-SAI ở cột dựng quan hệ), dòng chưa duyệt, ô lỗi công thức.
- Cột thuộc tính hỏng (GRPID của môi giới, GRPNAME, GRPLEVEL, JOINDATE) thì nhận dòng, để NULL, có test `not_null` mức warn.

**Vì sao chọn.** DEC-ELT-REJECT: raw vault giữ mọi dòng dựng được khóa. Loại cả dòng vì một thuộc tính hỏng sẽ làm mất phiên bản và gây "xóa giả" ở bản chụp đầy đủ (đề đã cảnh báo bẫy này ở CAP-KH).

## KT-19 (Cao): Xung đột giữa hai lô cùng `ingested_ts` lọt qua staging

**Vấn đề.** `stg_batch_dup_cols` gom theo `(batch_id, khóa)`. GT-STG-KEYTS lại xét `(khóa, ingested_ts)`.

**Lỗi xảy ra thế nào.** `ingested_ts` lấy `commit_ts` của manifest, nên hai lô của cùng bảng có thể trùng `ingested_ts` (lô sửa gửi cùng giây với lô gốc). Mỗi lô tự sạch nên cả hai dòng đều vào view hợp lệ. Raw vault nhận hai phiên bản cùng thời điểm thấy và không biết bản nào thấy trước. Phép thử âm trên DB thử (lô `CAP-MG-9999` cùng `ingested_ts` với `CAP-MG-0002`, BRK001 khác email) làm GT-STG-KEYTS đỏ với code chưa sửa.

**Khắc phục.** Gom theo `(ingested_ts, khóa)`, xếp hạng `order by batch_id, source_row_no`. Xung đột giữa hai lô cùng `ingested_ts` thành `CONFLICT_IN_BATCH` cho mọi dòng của khóa đó.

**Vì sao chọn.**
- Mọi dòng của một lô cùng `ingested_ts`, nên cách gom mới bao trọn cách cũ: dữ liệu đề không đổi số dòng ở cả 12 view.
- Vẫn không phụ thuộc cửa sổ nạp (KT-03): view không lọc gì, chỉ đổi khóa gom.
- Phương án "giữ bản `batch_id` lớn hơn" bị loại: `batch_id` là mã do nguồn đặt, không phải thứ tự thời gian, nên chọn theo nó là tùy tiện. Không xếp được thì loại cả hai, để D-DQ báo và nguồn gửi lại.

**Bằng chứng.** DB thử: code mới loại cả 2 dòng (`CONFLICT_IN_BATCH`), KEYTS xanh; đổi lại `partition by batch_id` thì KEYTS đỏ 1 khóa. Database thật: số dòng 12 view không đổi.

## KT-20 (Trung bình): Không test nào bắt khử trùng hỏng; phép thử âm KEYTS ghi sai

**Vấn đề.** GT-STG-KEYTS đếm `count(distinct hashdiff) > 1`; GT-STG-RECON chỉ kiểm tổng; không có test `unique`. Phép thử âm ghi trong `test_stg_keyts.sql` ("bỏ nhánh CONFLICT_IN_BATCH rồi chèn dòng xung đột thì đỏ") không đúng.

**Lỗi xảy ra thế nào.** Chạy thật trên máy và DB thử:
- Xóa nhánh `DUPLICATE_EVENT`: 12 sự kiện gửi hai lần trong `CAP-MG-0060` (cùng hashdiff) vào view hợp lệ. KEYTS và RECON vẫn xanh.
- Chỉ xóa nhánh `CONFLICT_IN_BATCH`: dòng xung đột thứ hai rơi vào `DUPLICATE_ROW`, dòng đầu vào view hợp lệ. KEYTS vẫn xanh vì chỉ còn một hashdiff.

**Khắc phục.** Test `finova-dbt/tests/staging/test_stg_dedup.sql`, hai vế, cùng cách gom `(ingested_ts, khóa)` với macro:
- `DUP_KEPT_TWICE`: mỗi `(ingested_ts, khóa)` có tối đa một dòng hợp lệ.
- `DUP_NOT_IDENTICAL`: dòng bị loại `DUPLICATE_ROW`/`DUPLICATE_EVENT` phải cùng hashdiff với dòng được giữ.

Sửa lại mô tả phép thử âm ở đầu `test_stg_keyts.sql`.

**Bằng chứng.** Xem bảng KT-07: xóa nhánh trùng thì `DUP_KEPT_TWICE` đỏ 12; xóa nhánh xung đột thì `DUP_NOT_IDENTICAL` đỏ 1.

## KT-21 (Thấp): Cột có mẫu `null_and_count` không kiểm mẫu; giờ thiết bị sai bị thay âm thầm

**Vấn đề.**
- Hợp đồng khai mẫu và `on_invalid: null_and_count` cho `GRPID` (broker), `PARENTID`, `GRPLEVEL` (regrp), `outcome`, `duration_sec` (events). Staging chỉ trim và viết hoa, không kiểm mẫu.
- `raw_event_ts` có gửi nhưng sai định dạng thì `event_ts` lùi về `server_ts` mà không có cờ.

**Lỗi xảy ra thế nào.** `GRPID = 'X1'` vẫn sinh `regrp_hk` và link môi giới - nhóm trỏ tới đơn vị không có trong hub. `duration_sec = '-5'` hay `'1,500'` vẫn được nhận thành số. Giờ thiết bị sai không phân biệt được với giờ thiết bị không gửi, nên D-DQ không đếm được. Dữ liệu đề hiện không có ca nào.

**Khắc phục.**
- Macro `stg_code_fmt(col, pattern)` (sai mẫu thì NULL) và `stg_parse_uint(col, pattern)` (số nguyên không dấu) trong `stg_parsers.sql`, áp cho 5 cột trên với đúng mẫu của hợp đồng.
- Cột `is_device_ts_invalid` ở `stg_finova_app__events` (và `__rejected`), có `not_null` trong `schema.yml`.
- Test warn `test_stg_attr_nulled.sql`: mỗi ô có giá trị ở landing nhưng NULL ở view hợp lệ là một dòng, cho 10 cột thuộc tính (gồm cả các cột ngày). Đây là phần "count" của `null_and_count`, làm nguồn cho D-DQ.

**Vì sao chọn.** Giữ dòng, để NULL đúng như hợp đồng (KT-18, DEC-ELT-REJECT). Một test đếm chung dựa trên so landing với staging thay cho từng test `not_null` riêng, vì `PARENTID`, `outcome`, `duration_sec` được phép NULL nên `not_null` không dùng được.

**Bằng chứng.** DB thử: `GRPID = 'X1'` và `raw_event_ts = '20/04/2026 9h'` cho `test_stg_attr_nulled` warn 2, `not_null_stg_flex__broker_grpid` warn 1, sự kiện có `is_device_ts_invalid = true` và `event_ts = server_ts`. Database thật: test xanh, số dòng không đổi.

## KT-22 (Cao): `DUP_CONTENT` bỏ qua bản chụp quay về nội dung cũ

**Vấn đề.** `process_single_batch` coi lô là `DUP_CONTENT` khi `content_hash` trùng **bất kỳ** lô LOADED nào của cùng bảng. Phát hiện khi dựng raw vault (RV-05 trong `docs/ky_thuat_raw_vault.md`).

**Lỗi xảy ra thế nào.** Bản chụp regrp `CAP-MG-0032` (27/04) bỏ G7, nên trùng byte với lô 17/04 (trước khi G7 xuất hiện ở lô 23/04). Lô bị bỏ qua, landing không có bản chụp không-G7, và vault chỉ biết G7 biến mất từ lô 04/05. Cây các ngày 27/04 – 03/05 vì vậy vẫn có G7 (trỏ tới CN9). `CAP-MG-0066` (G5/G6 về lại CN3) cũng bị bỏ, nhưng vô hại vì dòng tạo vòng đã bị loại ở staging. Các bảng khác không có trường hợp này.

**Khắc phục.** So `content_hash` với lô LOADED **gần nhất** của bảng (theo `log_id`). Test `test_tc_cap_ldz_03b_snapshot_revert_is_loaded`: A, B, A2 (trùng A) đều LOADED; gửi tiếp A3 trùng A2 thì `DUP_CONTENT`.

**Vì sao chọn.**
- Đề cố ý bỏ qua bản chụp không đổi qua nhiều ngày (mục 7.2), tức trùng lô liền trước. Bản chụp quay về trạng thái cũ là thay đổi thật, chính là trường hợp A → B → A mà PT-ABA đòi ba phiên bản.
- Phương án "so trong cùng business_date" bị loại: bản chụp không đổi của ngày mới sẽ được nạp hết, trái mục 7.2.
- Lô phát lại mang giờ cũ (khác lô gần nhất) giờ được nạp, rồi T-GUARD chặn ở runner (mục 2.3.1). Đó là đúng hành vi đề yêu cầu.

**Bằng chứng.** Loader trên dữ liệu đề: 63 lô `LOADED` (5.959 dòng), 41 `SKIPPED_DUP`; trước khi sửa là 61 và 43. Phép thử âm: dùng lại truy vấn cũ thì test đỏ (A2 thành `DUP_CONTENT`).

**Sửa sổ đã nạp bằng loader cũ.** Lệnh `python -m loader.load --recheck-dup` xét lại các lô `DUP_CONTENT` chưa từng LOADED, theo `arrival_seq`, so với lô LOADED liền trước của bảng theo `arrival_seq`. Không so theo `log_id`, vì lô nạp lại mang `log_id` mới nhưng vẫn đứng ở vị trí cũ trong chuỗi bản chụp. Lô vẫn trùng thì không ghi thêm sổ, nên chạy lại không đổi gì. Test `test_tc_cap_ldz_03c_recheck_dup_reloads_wrongly_skipped`.

---

## Ghi nhận, không sửa

| Điểm | Lý do giữ nguyên |
|---|---|
| Loader đổi ô rỗng `''` thành NULL ở landing | CSV không phân biệt được rỗng với NULL. Staging xử lý cả hai như nhau (`nullif(btrim(x), '')`), nên không mất thông tin |
| JSON Lines lưu từng khóa thành cột text bằng `str()` | Đúng với dữ liệu đề (chỉ có chuỗi và số nguyên). Nếu nguồn có boolean hoặc số thực, `str()` sẽ ra `True`, `12.0`; khi đó nên lưu thêm nguyên dòng vào một cột jsonb |
| Ô Excel dạng số hoặc ngày | Loader ghi ô bằng `str()`. File đề chỉ có cột C (số khách mới) là số nguyên, các cột khác là chuỗi (`'11,5'`), nên đúng. Nếu người nhập để ô dạng ngày, `str(datetime)` ra `'2026-04-20 00:00:00'`, `stg_parse_date` không nhận nên dòng bị loại nhầm `UNAPPROVED_ROW`; ô số thực `1.234` bị đọc thành 1234 theo quy tắc dấu phẩy thập phân. Sửa ở loader, commit riêng (việc còn mở 4) |

## Việc còn mở

Đã xong ngày 02/11/2026: dựng lại database thật và chạy `uv run dbt`, `uv run pytest` trên máy thật (xem "Môi trường kiểm chứng"); chuyển sang nhánh `feat/cap-mg-phucnd`; README (D-RUNBOOK); `docs/matran_test.md` (D-TEST, phần staging).

1. ~~Raw vault gọi `{{ dv_window() }}` và tự khử trùng giữa các lô; khóa vắng khỏi bản chụp mới thì ghi nhận xóa.~~ Đã xong 02/11/2026: xem `docs/ky_thuat_raw_vault.md`. Khóa vắng mặt ghi ở bảng `sts_*` thay cho `is_deleted` của DEC-MG-D4 (RV-03).
2. Business Vault phải tách người theo `[join_date, leave_date]` (KT-02), tính `is_active` (KT-15), chọn phân công khi chồng lấn (DEC-CAP-MG-OVERLAP; 12 cặp chồng lấn trong cùng lô ở dữ liệu đề) và bắt bẫy `FRDATE < JOINDATE` của BRK017 bằng phép ghép theo hiệu lực (môi giới và phân công nằm ở các lô khác nhau nên staging không ghép được).
3. D-DQ: bảng `dq_*` và `docs/chatluong.md` dựng từ các view `__rejected` và `test_stg_attr_nulled`, cùng cách đếm với GT-STG-RECON.
4. Loader: chuẩn hóa ô Excel dạng ngày (`YYYY-MM-DD`) và số (định dạng cố định) trước khi ghi landing (xem "Ghi nhận, không sửa").
5. Chạy lại trên máy thật các phép thử âm KT-07 còn ghi kết quả của môi trường thay thế.
