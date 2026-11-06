# Báo cáo chất lượng dữ liệu — CAP-MG (D-DQ)

- **Nguồn số:** bảng `mart.dq_mg_daily` (Phụ lục C, Bảng 75), dựng theo ngày D cùng Gold. Logic ở `docs/ky_thuat_gold.md` GD-06.
- **Kỳ:** 19 ngày giao dịch, 17/04 → 15/05/2026. Số đối chiếu lại ngày 06/11/2026 trên database dựng mới theo D-RUNBOOK.
- **Đối chiếu:**
  - Tổng `rows_landing` = 5.959, bằng số dòng loader đã nạp.
  - Tổng `rows_rejected` = 39, bằng `ctrl.reject_count` và tổng các view `__rejected`: sự kiện 19, phân công 10, chỉ tiêu 8, cây đơn vị 2, môi giới 0, NAV 0.
  - Đủ 104 lô của `ctrl.batch_log`: 63 `LOADED`, 41 `SKIPPED_DUP`.
  - Mỗi lô `LOADED` có `rows_landing = rows_valid + rows_rejected`. Test `test_gold_dq_recon` kiểm cả ba điều trên ở mỗi lần dựng.
  - Database `cap_mg_phucnd` dùng để phát triển có 106 dòng `ctrl.batch_log` (43 `SKIPPED_DUP`): `CAP-MG-0032`, `CAP-MG-0066` có thêm dòng `SKIPPED_DUP` cũ từ trước KT-22, trước khi `--recheck-dup` nạp lại hai lô này. `dq_mg_daily` vẫn đủ 104 lô. Database dựng mới có đúng 104 dòng.

Truy vấn lại:

```sql
select business_date, as_of_date, batch_id, source_table, rows_landing, rows_valid, rows_rejected,
       defect_code, reason_code, key_count, key_sample, handling, test_id
from mart.dq_mg_daily
order by as_of_date, batch_id, reason_code nulls first;
```

## Tóm tắt theo ngày

Ngày D gồm các lô có `ingested_ts` trong (cutoff của ngày giao dịch trước, cutoff(D)]; lô bỏ qua xếp theo `business_date`. Vì vậy lô sự kiện cuối tuần vào ngày giao dịch kế tiếp.

| Ngày D | Lô | Lô bỏ qua (trùng nội dung) | Dòng landing | Hợp lệ | Bị loại | Lỗi phát hiện |
|---|---|---|---|---|---|---|
| 17/04 | 4 | 0 | 434 | 434 | 0 | — |
| 20/04 | 5 | 3 | 229 | 229 | 0 | — |
| 21/04 | 6 | 3 | 253 | 249 | 4 | DQ-CHUADUYET, DQ-CONGTHUC (file chỉ tiêu v1) |
| 22/04 | 5 | 2 | 438 | 436 | 2 | DQ-NGAY-SAI |
| 23/04 | 5 | 2 | 252 | 252 | 0 | DQ-MOCOI |
| 24/04 | 5 | 2 | 247 | 247 | 0 | DQ-MOCOI |
| 27/04 | 7 | 2 | 256 | 256 | 0 | DQ-TUONGLAI |
| 28/04 | 5 | 3 | 227 | 227 | 0 | — |
| 29/04 | 5 | 3 | 233 | 233 | 0 | — |
| 04/05 | 9 | 0 | 492 | 490 | 2 | DQ-NGAY-SAI, DQ-CHONGLAN |
| 05/05 | 5 | 3 | 252 | 240 | 12 | DQ-TRUNG-NGUYEN |
| 06/05 | 6 | 1 | 488 | 480 | 8 | DQ-VONG, DQ-NGAY-SAI, DQ-CHONGLAN, DQ-CHUADUYET, DQ-CONGTHUC (file chỉ tiêu v2), DQ-QUYEN |
| 07/05 | 5 | 2 | 247 | 247 | 0 | — |
| 08/05 | 5 | 2 | 469 | 467 | 2 | DQ-NGAY-SAI, DQ-CHONGLAN |
| 11/05 | 7 | 1 | 502 | 500 | 2 | DQ-NGAY-SAI, DQ-CHONGLAN, DQ-KHOA-TAISUDUNG |
| 12/05 | 5 | 3 | 229 | 222 | 7 | DQ-KHOA-NULL, DQ-MA-LA |
| 13/05 | 5 | 3 | 238 | 238 | 0 | DQ-QUYEN |
| 14/05 | 5 | 3 | 234 | 234 | 0 | — |
| 15/05 | 5 | 3 | 239 | 239 | 0 | — |

## Giải thích từng mã lỗi

| Mã DQ | `reason_code` | Hướng xử lý | Số lần, số khóa | Ở đâu, khóa mẫu | Xử lý trong hệ thống | Test |
|---|---|---|---|---|---|---|
| DQ-NGAY-SAI | `INVALID_DATE_RANGE` | LOAI | 5 lô, 10 khóa | `flex_reaflnk`: phân công `AUTOID` 201, 202 có TODATE trước FRDATE, lặp ở mọi bản chụp từ 22/04 | Loại ở staging (`stg_flex__reaflnk__rejected`), không vào vault | GT-STG-RECON |
| DQ-MOCOI | `PARENT_MISSING` | CANHBAO | 2 lô, 2 khóa | `flex_regrp` 23/04, 24/04: `G7` trỏ cha `CN9` không có trong bản chụp | Nhận dòng. G7 không có môi giới nên không vào cây của ngày đó (DEC-CAP-MG-ORPHAN) | `test_stg_regrp_parent_missing` (warn) |
| DQ-VONG | `CYCLE_DETECTED` | LOAI | 1 lô, 2 khóa | `flex_regrp` lô `CAP-MG-0061` (06/05): `G5`, `G6` trỏ vòng vào nhau | Loại ở staging; cây 06/05 giữ phiên bản trước, `G5`, `G6` dưới `CN3` (DEC-CAP-MG-CYCLE) | `test_stg_regrp_no_cycle`, TC-CAP-MG-TREE |
| DQ-CHONGLAN | `ASSIGNMENT_OVERLAP` | QUYETDINH | 4 lô, 3 khóa mỗi lô | `flex_reaflnk` từ 04/05: `9994000026`, `9994000027`, `9994000028` có hai môi giới với khoảng hiệu lực giao nhau | Nhận dòng; Gold chọn một môi giới theo DEC-CAP-MG-OVERLAP (BRK021), `care_basis` chứa `DEC-CAP-MG-OVERLAP` | TC-CAP-MG-ONEBROKER |
| DQ-KHOA-TAISUDUNG | `KEY_REUSED` | QUYETDINH | 1 lô, 1 khóa | `flex_broker` lô `CAP-MG-0079` (11/05): `BRK017` đổi JOINDATE, tức người khác nhận mã | Khóa hub theo mã, tách người bằng satellite; Gold tính theo khoảng làm việc của người mang mã (DEC-CAP-MG-BROKERKEY) | `test_stg_broker_hk_consistent`, P-MG-REUSE |
| DQ-TRUNG-NGUYEN | `DUPLICATE_EVENT` | SUA | 1 lô, 12 khóa | `finova_app_events` lô `CAP-MG-0060` (05/05): 12 sự kiện gửi lặp | Khử trùng theo `event_id`: giữ một dòng, dòng lặp vào `__rejected` | GT-STG-UNIQUE |
| DQ-TUONGLAI | `FUTURE_TS_FIXED` | SUA | 1 lô, 6 khóa | `finova_app_events` lô `CAP-MG-0036` (vào ngày 27/04): giờ thiết bị lệch quá server_ts + 5 phút | Dùng `server_ts`, gắn cờ `is_future_ts_fixed`; dòng vẫn hợp lệ | TC-CAP-MG-EVENTTIME |
| DQ-KHOA-NULL | `KEY_NULL` | LOAI | 1 lô, 4 khóa | `finova_app_events` lô `CAP-MG-0087` (12/05): sự kiện không có `broker_id` | Loại ở staging | GT-STG-RECON |
| DQ-MA-LA | `ALLCODE_UNKNOWN` | LOAI | 1 lô, 3 khóa | `finova_app_events` lô `CAP-MG-0087`: `event_type` không có trong `event_type.csv` | Loại ở staging | GT-STG-RECON |
| DQ-QUYEN | `EVENT_NOT_ASSIGNED` | CANHBAO | 2 lô, 7 khóa | `finova_app_events` 06/05 (BRK005: 2), 13/05 (BRK009: 5): tương tác với tiểu khoản không giao cho môi giới vào ngày đó, theo phân công hệ thống biết tại cutoff(D) | Nhận dòng; không tính vào tử của CAP-MG-COVER30, vẫn tính vào số tương tác 30 ngày (DEC-CAP-MG-INTER30) | `test_dq_quyen_not_in_cover30`, `test_dq_quyen_events_have_no_assignment` |
| DQ-CHUADUYET | `UNAPPROVED_ROW` | LOAI | 2 lô, 3 khóa mỗi lô | `manual_kpi` v1 (`CAP-MG-0103`), v2 (`CAP-MG-0104`): `BRK012`, `BRK013`, `BRK014` chưa có người duyệt | Loại ở staging; các môi giới đó không có chỉ tiêu | TC-CAP-MG-EXCEL |
| DQ-CONGTHUC | `FORMULA_ERROR` | LOAI | 2 lô, 1 khóa mỗi lô | `manual_kpi` v1, v2: dòng `BRK021` có ô lỗi công thức | Loại cả dòng (DEC-CAP-MG-STAGING-RULES) | TC-CAP-MG-EXCEL |
| — | `DUP_CONTENT` | — | 41 lô | Bản chụp REGRP, BROKER, REAFLNK trùng nội dung lô LOADED liền trước | Loader bỏ qua (mục 2.3); không phải lỗi dữ liệu | TC-CAP-LDZ-03 |

## Lỗi không có dòng trong `dq_mg_daily`

- **DQ-EXCEL** (tiêu đề hai dòng, ô gộp, số ghi dạng chữ): loader và staging sửa theo cấu trúc file. Đây không phải lỗi của từng dòng; TC-CAP-MG-EXCEL kiểm việc đọc đúng.
- **TH-NGHIVIEC / DEC-CAP-MG-GAP:** khoảng trống 01–03/05 của BRK017 không có ngày giao dịch, nên Gold không có tiểu khoản nào mang cờ `is_carer_inactive`.
- **DQ-PII:** `FULLNAME`, `EMAIL`, `MOBILE` của `flex_broker` và họ tên của `manual_kpi` là cột định danh có sẵn, không phải dòng lỗi. Staging che email, số điện thoại; họ tên chỉ đi vào hash; Gold không có các cột này (GT-STG-PII, `dv_shape`).
- **Lỗi file** (DQ-FILE-HONG: `FILE_MISSING`, `SHA256_MISMATCH`, `ROWCOUNT_MISMATCH`): gói đề không có lô nào bị từ chối. Nếu có, dòng sẽ mang `handling = TUCHOI_LO`.
