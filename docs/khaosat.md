# Báo cáo Khảo sát Dữ liệu Nguồn — Đề CAP-MG (D-KHAOSAT)

> Viết trước khi có model. Đính chính ngày 06/11/2026 sau khi đối chiếu lại với file gốc: xem mục 5.

## 1. Tổng quan Bộ dữ liệu
- **Kỳ dữ liệu:** Từ `2026-04-17` (lô khởi tạo) đến `2026-05-15` (19 ngày giao dịch; nghỉ lễ `30/04`–`01/05` và các ngày cuối tuần theo `ref/calendar.csv`).
- **Tổng số lô trong `manifest.csv`:** **104 lô** chia cho 6 bảng nguồn.
- **Tổng số dòng dữ liệu:** **9.261 dòng** (tính theo `row_count` khai báo trong `manifest.csv`; nếu tính cả 4 dòng tiêu đề của 2 file Excel là 9.265 dòng vật lý).
- **Danh mục tham chiếu (`ref/`):**
  - `event_type.csv`: 4 mã hợp lệ (`CALL`, `MEET`, `MSG`, `NOTE`).
  - `org_roles.csv`: 4 bản ghi phân quyền RLS (`LEAD-G2`: `TRUONG_NHOM` phạm vi `G2`; `GD-CN1`: `GIAM_DOC_CN` phạm vi `CN1`; `BRK003`: `MOI_GIOI` phạm vi `BRK003`; `BRK009`: `MOI_GIOI` phạm vi `BRK009`).
  - `calendar.csv`: 36 ngày lịch (`2026-04-17` đến `2026-05-22`).

### Bảng 1. Thống kê tổng hợp 6 bảng nguồn

| Bảng landing (`source_table`) | Định dạng | Số lô | Số lô trùng nội dung (`SKIPPED_DUP`) | Tổng số dòng đọc | Khóa nghiệp vụ (BK) | Số giá trị BK phân biệt | Cột có giá trị NULL (số dòng NULL) |
|---|---|---:|---:|---:|---|---:|---|
| `flex_regrp` | CSV | 19 | 12 | 192 | `GRPID` | 11 | `PARENTID` (19 dòng của nút gốc `HO`, 9,90%) |
| `flex_broker` | CSV | 19 | 16 | 456 | `BROKERID` | 24 (25 người thật) | `LEAVEDATE` (451/456 dòng, 98,90%) |
| `flex_reaflnk` | CSV | 19 | 13 | 4.114 | `AUTOID` | 237 | Không có (0) |
| `ref_nav` | CSV | 19 | 0 | 3.800 | `TXDATE`, `AFACCTNO` | 19 ngày × 200 TK | Không có (0) |
| `finova_app_events` | JSONL | 26 | 0 | 653 | `event_id` | 641 | `broker_id` (4 dòng rỗng `""`, 0,61%) |
| `manual_kpi` | XLSX | 2 | 0 | 46 (data) / 50 (raw) | `broker_id` | 23 | `Người duyệt`, `Ngày duyệt` (6/46 dòng, 13,04%) |

---

## 2. Phân bố cột và Giá trị phân biệt (Distinct Count) theo từng bảng

1. **`flex_regrp` (19 lô, 192 dòng):**
   - Cột: `GRPID` (11), `PARENTID` (7 + NULL), `GRPNAME` (11), `GRPLEVEL` (3 cấp: `0` Hội sở, `1` Chi nhánh, `2` Nhóm), `EFFDATE` (4), `STATUS` (1 giá trị `'A'`).
   - Có 7 lô đổi nội dung so với lô liền trước: `CAP-MG-0001` (`17/04`), `CAP-MG-0020` (`23/04`, thêm `G7`), `CAP-MG-0025` (`24/04`, `G7` đổi `EFFDATE`), `CAP-MG-0032` (`27/04`, `G7` biến mất, quay về nội dung `CAP-MG-0001`), `CAP-MG-0051` (`04/05`, `G4` đổi cha), `CAP-MG-0061` (`06/05`, vòng `G5`, `G6`), `CAP-MG-0066` (`07/05`, quay về nội dung `CAP-MG-0051`). 12 lô còn lại trùng lô liền trước.
2. **`flex_broker` (19 lô, 456 dòng, mỗi lô 24 dòng):**
   - Cột: `BROKERID` (24 mã `BRK001`..`BRK024`), `FULLNAME` (25 tên), `GRPID` (6 nhóm `G1`..`G6`), `STATUS` (2 giá trị `'A'`, `'C'`), `EMAIL` (25), `MOBILE` (25), `JOINDATE` (25), `LEAVEDATE` (1 giá trị `'30/04/2026'` ở 5 lô từ `04/05` đến `08/05`).
   - Cột PII: `FULLNAME`, `EMAIL`, `MOBILE`.
   - Có 3 lô thực sự thay đổi nội dung: `CAP-MG-0002` (`17/04`), `CAP-MG-0052` (`04/05`), `CAP-MG-0079` (`11/05`).
3. **`flex_reaflnk` (19 lô, 4.114 dòng):**
   - Cột: `AUTOID` (237), `REACCTNO` (24), `AFACCTNO` (200 tiểu khoản `9994000001`..`9994000200`), `FRDATE` (153), `TODATE` (6), `STATUS` (1 giá trị `'A'`), `LASTCHANGE` (5).
   - Có 6 lô thực sự thay đổi nội dung: `CAP-MG-0003` (`17/04`, 200 dòng), `CAP-MG-0017` (`22/04`, 202 dòng), `CAP-MG-0053` (`04/05`, 218 dòng), `CAP-MG-0063` (`06/05`, 222 dòng), `CAP-MG-0073` (`08/05`, 237 dòng), `CAP-MG-0080` (`11/05`, 237 dòng).
4. **`ref_nav` (19 lô, 3.800 dòng):**
   - Cột: `TXDATE` (19 ngày giao dịch), `AFACCTNO` (200 tiểu khoản), `NAV` (3.787 giá trị số nguyên dương). Không có NULL, không có lỗi định dạng.
5. **`finova_app_events` (26 lô JSONL, 653 dòng từ `20/04` đến `15/05` kể cả ngày nghỉ và cuối tuần):**
   - Cột: `event_id` (641), `broker_id` (24 + rỗng), `afacctno` (193), `event_type` (5 giá trị: `CALL`, `MEET`, `MSG`, `NOTE`, và mã lạ `VIDEO`), `event_ts` (641), `server_ts` (641), `duration_sec` (458), `outcome` (3 giá trị: `REACHED`, `NO_ANSWER`, `FOLLOW_UP`).
6. **`manual_kpi` (2 lô Excel `.xlsx`, mỗi file 25 dòng gồm 2 dòng tiêu đề + 23 dòng dữ liệu):**
   - `CAP-MG-0103` (`kpi_targets_2026Q2_v1.xlsx`, `commit_ts = 2026-04-21T15:00:00+07:00`).
   - `CAP-MG-0104` (`kpi_targets_2026Q2_v2.xlsx`, `commit_ts = 2026-05-06T16:30:00+07:00`).

### Bảng 2. Tỷ lệ NULL của từng bảng

Tính trên toàn bộ dòng của mọi lô trong `manifest.csv`, kể cả lô trùng nội dung. Số giá trị khác nhau của từng cột ghi ở các mục trên. Cột không ghi ở đây không có NULL nào.

| Bảng | Số dòng | Cột có NULL | Số dòng NULL | Tỷ lệ NULL |
|---|---:|---|---:|---:|
| `flex_regrp` | 192 | `PARENTID` | 19 | 9,90% |
| `flex_broker` | 456 | `LEAVEDATE` | 451 | 98,90% |
| `flex_reaflnk` | 4.114 | Không có | 0 | 0,00% |
| `ref_nav` | 3.800 | Không có | 0 | 0,00% |
| `finova_app_events` | 653 | `broker_id` | 4 | 0,61% |
| `manual_kpi` | 46 | `Người duyệt`, `Ngày duyệt` | 6 | 13,04% |

### Bảng 3. Phân bố số dòng theo ngày nghiệp vụ (`business_date` của `manifest.csv`)

Lô sự kiện có cả ngày nghỉ và cuối tuần; bốn bảng FLEX chỉ có ở 19 ngày giao dịch. `flex_reaflnk` tăng từ 200 lên 237 dòng vì nguồn thêm phân công mới và vẫn giữ phân công cũ.

| Ngày | `flex_regrp` | `flex_broker` | `flex_reaflnk` | `ref_nav` | `finova_app_events` | `manual_kpi` | Tổng |
|---|---:|---:|---:|---:|---:|---:|---:|
| 17/04 | 10 | 24 | 200 | 200 | | | 434 |
| 20/04 | 10 | 24 | 200 | 200 | 29 | | 463 |
| 21/04 | 10 | 24 | 200 | 200 | 30 | 23 | 487 |
| 22/04 | 10 | 24 | 202 | 200 | 36 | | 472 |
| 23/04 | 11 | 24 | 202 | 200 | 41 | | 478 |
| 24/04 | 11 | 24 | 202 | 200 | 36 | | 473 |
| 25/04 | | | | | 3 | | 3 |
| 26/04 | | | | | 6 | | 6 |
| 27/04 | 10 | 24 | 202 | 200 | 37 | | 473 |
| 28/04 | 10 | 24 | 202 | 200 | 27 | | 463 |
| 29/04 | 10 | 24 | 202 | 200 | 33 | | 469 |
| 30/04 | | | | | 5 | | 5 |
| 01/05 | | | | | 3 | | 3 |
| 02/05 | | | | | 5 | | 5 |
| 03/05 | | | | | 3 | | 3 |
| 04/05 | 10 | 24 | 218 | 200 | 24 | | 476 |
| 05/05 | 10 | 24 | 218 | 200 | 52 | | 504 |
| 06/05 | 10 | 24 | 222 | 200 | 33 | 23 | 512 |
| 07/05 | 10 | 24 | 222 | 200 | 37 | | 493 |
| 08/05 | 10 | 24 | 237 | 200 | 32 | | 503 |
| 09/05 | | | | | 4 | | 4 |
| 10/05 | | | | | 3 | | 3 |
| 11/05 | 10 | 24 | 237 | 200 | 34 | | 505 |
| 12/05 | 10 | 24 | 237 | 200 | 29 | | 500 |
| 13/05 | 10 | 24 | 237 | 200 | 38 | | 509 |
| 14/05 | 10 | 24 | 237 | 200 | 34 | | 505 |
| 15/05 | 10 | 24 | 237 | 200 | 39 | | 510 |
| **Tổng** | **192** | **456** | **4.114** | **3.800** | **653** | **46** | **9.261** |

---

## 3. Danh mục Lỗi dữ liệu (`DQ-*`) phát hiện trong Bộ dữ liệu

| Mã lỗi | Bảng nguồn | Lô (`batch_id`) / File | Số lượng lỗi | Khóa / Dòng ví dụ cụ thể | Hướng xử lý đề xuất |
|---|---|---|---:|---|---|
| **DQ-NGAY-SAI** | `flex_reaflnk` | Từ `CAP-MG-0017` (`reaflnk_20260422.csv`) đến `CAP-MG-0100` (16 file, 32 dòng; chỉ 5 lô `LOADED` nên 10 dòng vào `__rejected`) | 2 khóa / lô | `AUTOID=201` (`AFACCTNO=9994000029`) và `AUTOID=202` (`AFACCTNO=9994000030`): `FRDATE=20/05/2026 > TODATE=01/05/2026` | **LOAI**: Đưa sang `stg_flex__reaflnk__rejected` với `reason_code = 'INVALID_DATE_RANGE'`. |
| **DQ-MOCOI** | `flex_regrp` | `CAP-MG-0020` (`regrp_20260423.csv`), `CAP-MG-0025` (`regrp_20260424.csv`) | 1 khóa / lô (2 dòng) | `GRPID=G7` có `PARENTID=CN9` (đơn vị cha `CN9` không tồn tại trong `flex_regrp`) | **CANHBAO**: Nhận khóa vào Hub/Link; test cảnh báo (`severity: warn`) và ghi nhận vào bảng chất lượng `dq_*`. |
| **DQ-VONG** | `flex_regrp` | `CAP-MG-0061` (`regrp_20260506.csv`) | 2 nút (1 vòng) | `GRPID=G5` (`PARENTID=G6`) và `GRPID=G6` (`PARENTID=G5`) tạo chu trình `G5 -> G6 -> G5` | **LOAI / QUYETDINH (`DEC-CAP-MG-CYCLE`)**: Phát hiện vòng ở staging/BV, loại cặp cạnh tạo vòng và giữ phiên bản cây hợp lệ liền trước (`CN3`) cho ngày `06/05`. |
| **DQ-CHONGLAN** | `flex_reaflnk` | Từ `CAP-MG-0053` (`reaflnk_20260504.csv`) đến `CAP-MG-0073` (`08/05`) | 3 tiểu khoản | `AFACCTNO` in (`9994000026`, `9994000027`, `9994000028`): `AUTOID 26..28` (`BRK010`, `TODATE=31/12/9999`) chồng lấn với `AUTOID 216..218` (`BRK021`, `FRDATE=04/05/2026`, `TODATE=31/12/9999`). Tới lô `CAP-MG-0080` (`11/05`) nguồn đóng `AUTOID 216..218` ở `TODATE = 08/05/2026`; `AUTOID 26..28` vẫn giữ `31/12/9999`, nên từ `09/05` tiểu khoản quay về `BRK010` và hai khoảng hiệu lực vẫn giao nhau ở `04–08/05`. | **QUYETDINH (`DEC-CAP-MG-OVERLAP`)**: Áp dụng quy tắc phân công có `FRDATE` muộn hơn (hoặc `AUTOID`/phiên bản biết sau) thắng (`BRK021` thắng từ `04/05`) để thỏa `C-SA-ONEBROKER`. |
| **DQ-KHOA-TAISUDUNG** | `flex_broker` | `CAP-MG-0079` (`broker_20260511.csv`) đến `CAP-MG-0099` | 1 mã (2 người) | `BROKERID=BRK017`: từ `17/04`–`08/05` là `Ngô Đức Châu` (`JOINDATE=14/05/2025`, nghỉ `30/04/2026`); từ `11/05` cấp lại cho `Lý Minh Sơn` (`JOINDATE=11/05/2026`). | **QUYETDINH (`DEC-CAP-MG-BROKERKEY`)**: Xác định khóa Hub môi giới và tách lịch sử/chỉ số giữa người cũ và người mới. |
| **DQ-TRUNG-NGUYEN** | `finova_app_events` | `CAP-MG-0060` (`app_events_20260505.jsonl`) | 12 dòng lặp | 12 `event_id` xuất hiện 2 lần y hệt trong lô (ví dụ `8416b4be-11c0-9b27-5c1e-2b27abacf591`, `53dddb1c-055a-8fea-ea23-4597f02e10d5`...) | **SUA**: Khử trùng (deduplicate) theo `event_id` ở `stg_finova_app__events`, giữ 1 dòng duy nhất. |
| **DQ-TUONGLAI** | `finova_app_events` | `CAP-MG-0036` (`app_events_20260427.jsonl`) | 6 dòng | 6 sự kiện có `event_ts` ngày `2026-04-30` trong khi `server_ts` là `2026-04-27` (ví dụ `event_id=59f6cf75-60cf-ed72-25a2-18de989c3c02`: `event_ts=2026-04-30T13:45:38+07:00`, `server_ts=2026-04-27T13:46:07+07:00`) | **SUA**: Khi `event_ts > server_ts + 5 phút` (ngưỡng cấu hình), thay `event_ts` bằng `server_ts` và gắn cờ `is_future_ts_fixed = true`. |
| **DQ-KHOA-NULL** | `finova_app_events` | `CAP-MG-0087` (`app_events_20260512.jsonl`) | 4 dòng | Dòng 9 (`4a34a6e2...`), dòng 12 (`e8e77718...`), dòng 19 (`2a16a6f3...`), dòng 20 (`06f50576...`) có `broker_id = ""` | **LOAI**: Đưa sang `stg_finova_app__events__rejected` với `reason_code = 'KEY_NULL'`. |
| **DQ-MA-LA** | `finova_app_events` | `CAP-MG-0087` (`app_events_20260512.jsonl`) | 3 dòng | Dòng 6 (`7bc715cc...`), dòng 10 (`8216a544...`), dòng 28 (`6f9e7d81...`) có `event_type = 'VIDEO'` (không có trong `ref/event_type.csv`) | **LOAI**: Đưa sang `stg_finova_app__events__rejected` với `reason_code = 'ALLCODE_UNKNOWN'`. |
| **DQ-QUYEN** | `finova_app_events` | `CAP-MG-0092` (`app_events_20260513.jsonl`) | 7 dòng theo điều hệ thống biết tại cutoff; thêm 4 dòng nếu xét theo phân công biết về sau | Trong `CAP-MG-0092` (`13/05`), `BRK009` ghi 5 tương tác (`43350137...`, `ce347490...`, `3e071bae...`, `405f36b2...`, `fa30eaa4...`) với các tiểu khoản `9994000023, 126, 092, 161, 175` không do `BRK009` chăm sóc. Trong `CAP-MG-0065` (`06/05`), `BRK005` ghi 2 tương tác (`ab36056a...`, `f603fbed...`) với `9994000019`, `9994000017` đã chuyển cho `BRK012` ở lô `CAP-MG-0063` cùng ngày. 4 tương tác `27/04–05/05` của `BRK005` trên `9994000016`, `9994000018` chỉ thành sai quyền khi nhìn lại bằng lô `06/05` (lùi hiệu lực), nên as-of các ngày đó không tính là lỗi. | **CANHBAO**: Giữ sự kiện trong vault, đếm ở `dq_mg_daily` (`EVENT_NOT_ASSIGNED`); không tính vào tử số độ phủ `CAP-MG-COVER30`. |
| **DQ-EXCEL** | `manual_kpi` | `CAP-MG-0103` (`v1.xlsx`), `CAP-MG-0104` (`v2.xlsx`) | 2 file | Dòng 1–2 là tiêu đề 2 tầng có gộp ô `C1:E1`; cột `Số cuộc gọi` lưu kiểu text (`'300'`), cột `AUM tăng thêm` lưu kiểu text dùng dấu phẩy thập phân (`'10,5'`). | **SUA**: Bỏ 2 dòng tiêu đề ở staging, đổi dấu `,` thành `.` và ép kiểu `numeric`. |
| **DQ-CHUADUYET** | `manual_kpi` | `CAP-MG-0103` (`v1.xlsx`), `CAP-MG-0104` (`v2.xlsx`) | 3 dòng / file (6 dòng) | Dòng 14, 15, 16 (`BRK012`, `BRK013`, `BRK014`) có `Người duyệt = NULL` và `Ngày duyệt = NULL`. | **LOAI**: Đưa sang `stg_manual__kpi__rejected` với `reason_code = 'UNAPPROVED_ROW'`. |
| **DQ-CONGTHUC** | `manual_kpi` | `CAP-MG-0103` (`v1.xlsx`), `CAP-MG-0104` (`v2.xlsx`) | 1 dòng / file (2 dòng) | Dòng 22 (`BRK021` - Hồ Xuân Khánh) có ô `Số cuộc gọi = '#REF!'`. | **LOAI**: Đưa sang `stg_manual__kpi__rejected` với `reason_code = 'FORMULA_ERROR'`. |
| **DQ-PII** | `flex_broker`, `manual_kpi` | Toàn bộ các lô `flex_broker` và `manual_kpi` | 25 môi giới | Cột `FULLNAME`, `EMAIL`, `MOBILE` trong `flex_broker` và `Họ tên` trong `manual_kpi`. | **CANHBAO**: Đánh dấu `pii_columns` trong hợp đồng nguồn, tách/che ở tầng định danh; tuyệt đối không đưa vào các bảng Gold (`mart`). |

---

## 4. Các Tình huống Nghiệp vụ (`TH-*`) phát hiện trong Bộ dữ liệu

1. **`TH-GUILAI` (Lô gửi lặp nguyên nội dung):**
   - Có **41/104 lô** trùng nội dung lô liền trước của cùng bảng (`flex_regrp`: 12 lô, `flex_broker`: 16 lô, `flex_reaflnk`: 13 lô). Loader ghi `status = 'SKIPPED_DUP'`, `reason_code = 'DUP_CONTENT'` vào `ctrl.batch_log` và không ghi trùng vào `landing`.
   - Hai lô `flex_regrp` còn lại (`CAP-MG-0032`, `CAP-MG-0066`) trùng một lô cũ hơn nhưng khác lô liền trước, tức bản chụp quay về nội dung cũ. Loader phải nạp để raw vault thấy `A → B → A` (`TH-ABA`, KT-22). Nếu so với mọi lô đã nạp thì đếm được 43, và vault mất phiên bản.
2. **`TH-HIEULUCTUONGLAI` (Phân công nhập trước, hiệu lực sau — `P-MG-REASSIGN`):**
   - Tại lô `CAP-MG-0073` (`2026-05-08`, `commit_ts = 08/05 22:10`), xuất hiện 15 dòng `AUTOID 223..237` chuyển các tiểu khoản `9994000001..9994000015` từ `BRK003` sang `BRK009` với `FRDATE = 11/05/2026` (và sửa `TODATE` của `AUTOID 1..15` của `BRK003` thành `10/05/2026`).
   - Hệ quả: Tại `as-of 08/05`, người chăm sóc `9994000001..15` vẫn là `BRK003`; từ `as-of 11/05` mới chuyển sang `BRK009`.
3. **`TH-LUIHIEULUC` (Phân công nhập sau, hiệu lực lùi về quá khứ — `P-MG-BACKDATE`):**
   - Tại lô `CAP-MG-0063` (`2026-05-06`, `commit_ts = 06/05 22:10`), xuất hiện 4 dòng `AUTOID 219..222` phân công `BRK012` chăm sóc `9994000016..9994000019` với `FRDATE = 27/04/2026` (và đóng `TODATE` của `AUTOID 16..19` của `BRK005` về `26/04/2026`).
   - Hệ quả: Khi dựng lại `as-of 28/04` sau ngày `06/05`, do lọc `ingested_ts <= cutoff(28/04)`, hệ thống chưa biết lô `06/05` nên tiểu khoản `9994000016` tại `as-of 28/04` vẫn do **`BRK005`** chăm sóc.
4. **`TH-TAICAUTRUC` (Nhóm chuyển chi nhánh giữa kỳ — `P-MG-RESTRUCT`):**
   - Nhóm `G4` từ `17/04` đến `29/04` có `PARENTID = CN2`. Từ lô `CAP-MG-0051` (`2026-05-04`), `G4` đổi sang `PARENTID = CN1` (`EFFDATE = 04/05/2026`).
5. **`TH-NGHIVIEC` (Môi giới nghỉ việc, khoảng trống chăm sóc & cấp lại mã — `P-MG-REUSE`):**
   - `BRK017` (Ngô Đức Châu) có `LEAVEDATE = 30/04/2026`, `STATUS = C` ghi nhận ở lô `CAP-MG-0052` (`04/05`), đồng thời 13 tiểu khoản của `BRK017` (`AUTOID` 20–25, 41, 65, 89, 113, 137, 161, 185) đóng ở `03/05/2026` và chuyển sang `BRK018` từ `04/05/2026` (`AUTOID` 203–215). Đến lô `CAP-MG-0079` (`11/05`), mã `BRK017` được cấp cho nhân viên mới Lý Minh Sơn (`JOINDATE = 11/05/2026`). Người mới không có tiểu khoản nào và không có sự kiện nào: 16 sự kiện của mã `BRK017` đều nằm trong `20/04–29/04`, của người cũ.
6. **`TH-NHAPTAY` (Hai phiên bản file chỉ tiêu KPI — `P-MG-KPI`):**
   - Phiên bản `v1` (`CAP-MG-0103`, `commit_ts = 21/04 15:00`) áp dụng từ `21/04` đến `05/05`.
   - Phiên bản `v2` (`CAP-MG-0104`, `commit_ts = 06/05 16:30`) thay thế `v1` từ `as-of 06/05` trở đi (tăng chỉ tiêu cuộc gọi của `BRK003` 400 → 440, `BRK005` 500 → 540, `BRK007` 350 → 390, `BRK009` 450 → 490).
7. **`TH-VANGMAT` (Thực thể biến mất khỏi bản chụp):**
   - `G7` có ở `CAP-MG-0020`, `CAP-MG-0025`, vắng từ `CAP-MG-0032` (`27/04`). Vault đánh dấu `DELETED` ở `sts_regrp__flex`.
8. **`TH-ABA` (Giá trị quay về A):**
   - Cây đơn vị quay về nội dung cũ ở `CAP-MG-0032` và `CAP-MG-0066`. Hai dòng vòng ở `CAP-MG-0061` bị loại nên `G5`, `G6` không sinh phiên bản giả.
9. **Tình huống không có trong gói đề:** cả 104 dòng `manifest.csv` có `available_ts = commit_ts`, nên CAP-MG không có lô về muộn (`TH-VEMUON`) hay lô phát lại (`TH-DAOTHUTU`). T-GUARD chỉ được kiểm bằng lô giả trong pytest.

---

## 5. Đính chính ngày 06/11/2026

Bản đầu có các số sai, đã sửa ở các mục trên sau khi đối chiếu với file gốc:

| Chỗ | Bản đầu | Sửa thành |
|---|---|---|
| Lô trùng nội dung | 43 lô (`flex_regrp` 14) | 41 lô (`flex_regrp` 12); 2 lô quay về nội dung cũ vẫn được nạp |
| Lô `flex_regrp` đổi nội dung | 5 lô, liệt kê 6 | 7 lô, thêm `CAP-MG-0025` |
| `DQ-NGAY-SAI` | 15 lô, 30 dòng | 16 file, 32 dòng; 10 dòng vào `__rejected` |
| Tiểu khoản của `BRK017` | 12 | 13 |
| Sự kiện của người mới mang `BRK017` | "có từ 11/05" | Không có sự kiện nào |
| Cách nguồn gỡ `DQ-CHONGLAN` | Đóng `AUTOID 26..28` ở `03/05` | Đóng `AUTOID 216..218` ở `08/05` |
| `DQ-QUYEN` | 5 và 6 dòng, cờ `is_unauthorized` | 7 dòng tại cutoff, thêm 4 dòng khi nhìn lại; không có cờ này, số đếm ở `dq_mg_daily` |
| Thiếu | | Tỷ lệ NULL (Bảng 2), phân bố theo ngày (Bảng 3) |

