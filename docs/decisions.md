# Sổ Quyết định Thiết kế — Đề CAP-MG (D-QUYETDINH)

Tài liệu này ghi lại các quyết định thiết kế kiến trúc và nghiệp vụ cho đề **`CAP-MG` (Môi giới, đơn vị và chăm sóc)** theo yêu cầu tại Mục 7.3, Mục 7.4 (Bảng 69) và Phụ lục D của đề bài `FNV-CAP-DBT v1.5`. Mỗi quyết định trình bày tối thiểu hai phương án, phương án được chọn, căn cứ lựa chọn và tác động định lượng lên số liệu đầu ra.

---

## 1. `DEC-CAP-MG-BROKERKEY` — Tái sử dụng mã môi giới (`DQ-KHOA-TAISUDUNG`): Khóa Hub môi giới là gì?

### Bối cảnh & Dữ liệu thực tế

Mã **`BRK017`** được cấp cho hai người (số liệu kiểm trực tiếp trên gói đề):

| Nguồn | Diễn biến của `BRK017` |
| --- | --- |
| `flex_broker` | Từ lô `17/04`: **Ngô Đức Châu**, `JOINDATE = 14/05/2025`, `STATUS = A`, nhóm `G5`. Từ lô `04/05`: `STATUS = C`, `LEAVEDATE = 30/04/2026`. Từ lô `11/05`: dòng được **thay hẳn** bằng **Lý Minh Sơn**, `JOINDATE = 11/05/2026`, `STATUS = A` (bản chụp không còn giữ người cũ). |
| `flex_reaflnk` | 13 tiểu khoản gắn `BRK017`. Từ lô `04/05` các phân công đóng `TODATE = 03/05/2026` (khoảng trống `TH-NGHIVIEC` 01–03/05) và chuyển cho `BRK018` từ `04/05/2026`. Người mới không được giao tiểu khoản nào tới `15/05`. |
| `finova_app_events` | 16 sự kiện của `BRK017`, toàn bộ trong `20/04`–`29/04` (người cũ). Không có sự kiện nào từ `11/05`. |
| `manual_kpi` | Không có dòng `BRK017` ở cả hai phiên bản. |
| Bẫy | 4/200 phân công có `FRDATE` **trước** `JOINDATE` của môi giới, và cả 4 đều là `BRK017` (`AUTOID` 20, 65, 161, 185; `FRDATE` 03–04/2025 < `14/05/2025`). |

`flex_reaflnk`, `finova_app_events`, `manual_kpi` chỉ mang mã (`REACCTNO` / `broker_id`), không có `JOINDATE`. Hai nguồn sau không phải FLEX nên staging không được tra chéo sang `flex_broker` (Q19: chỉ tra khóa trong cùng nguồn).

### Các phương án cân nhắc

| Phương án | Thiết kế | Hệ quả (`P-MG-REUSE` tại `12/05`, `15/05`: người đang mang mã `BRK017`) |
| --- | --- | --- |
| **A (ĐƯỢC CHỌN): mã nguồn làm khóa hub, tách người bằng satellite** | `broker_hk = dv_hash('FLEX', BROKERID)` ở **mọi** staging. `JOINDATE` nằm trong hashdiff của satellite hồ sơ môi giới: cấp lại mã thì sinh phiên bản mới. Business Vault dựng khoảng làm việc `[JOINDATE, LEAVEDATE]` của người mang mã tại `D`; Gold chỉ tính phân công và tương tác nằm trong khoảng làm việc đó. `broker_key = BROKERID:JOINDATE` suy từ phiên bản hiệu lực tại `D`. | 0 tiểu khoản, `CAP-MG-BOOKNAV = 0`, 0 tương tác 30 ngày. Nếu Gold quên lọc theo khoảng làm việc: vẫn 0 tiểu khoản nhưng **16 tương tác** (sai, của người cũ) vì cửa sổ 30 ngày tới `12/05` hay `15/05` đều phủ `20–29/04`. Test bảo vệ: lọc theo khoảng làm việc trong `TC-CAP-MG-*` ở Gold. |
| **B: khóa ghép `(BROKERID, JOINDATE)`** | Hub là người. `flex_reaflnk` tra `JOINDATE` từ `flex_broker` ở staging; sự kiện và chỉ tiêu (khác nguồn) chỉ mang mã nên phải tra ở Business Vault, raw vault cần thêm hub theo mã và link nối hai hub. | Kết quả đúng như A nếu phép tra đúng. Tra theo `FRDATE` (người có `JOINDATE ≤ FRDATE`) **không ra người cho 4 phân công bẫy** của `BRK017`; tra theo người mang mã tại `ingested_ts` của lô buộc staging đọc landing `flex_broker` ngoài cửa sổ `(lo, hi]`, phụ thuộc thứ tự lô broker/reaflnk trong ngày và có rủi ro lệch giữa chạy theo ngày với full refresh (`PT-FULL`). |

### Quyết định chốt

Chọn **Phương án A**. Lý do:

1. Khóa hub là thứ cả bốn nguồn đều gửi, nên mọi link khớp hub mà không cần tra (`DEC-ELT-HUBSRC`, `GT-LNK-PARENT`). Test `tests/staging/test_stg_broker_hk_consistent.sql` chặn việc các staging tính `broker_hk` khác nhau.
2. Logic tách người chỉ nằm ở **một** chỗ (Business Vault/Gold, dựa trên phiên bản satellite đã lọc as-of), thay vì rải ở staging và Business Vault như B. Dù chọn phương án nào, sự kiện ứng dụng chỉ mang mã nên logic khoảng làm việc vẫn bắt buộc phải có.
3. Phù hợp tinh thần `DEC-SA-BROKERKEY`: tách "người" khỏi "mã", giữ mã môi giới quen dùng để tra cứu.

Đánh đổi chấp nhận: raw vault không tự phân biệt hai người của cùng mã; nếu Gold quên lọc theo khoảng làm việc thì số liệu của người mới bị lẫn người cũ (16 tương tác ở ví dụ trên). Người cũ biến khỏi bản chụp từ `11/05` thể hiện bằng phiên bản satellite mới, không phải bằng việc khóa hub vắng mặt.

---

## 2. `DEC-CAP-MG-OVERLAP` — Hai môi giới cùng hiệu lực trên một tiểu khoản (`DQ-CHONGLAN`): Tính cho ai?

### Bối cảnh & Dữ liệu thực tế

Từ lô `CAP-MG-0053` (`2026-05-04`) đến `CAP-MG-0073` (`2026-05-08`), có **3 tiểu khoản (`9994000026`, `9994000027`, `9994000028`)** có 2 bản ghi phân công `STATUS = 'A'` cùng thỏa mãn `FRDATE <= D <= TODATE`:

- Bản ghi cũ `AUTOID 26, 27, 28`: giao cho **`BRK010`**, `FRDATE` từ năm `2025`, `TODATE = 9999-12-31` (do nguồn quên đóng `TODATE` khi chuyển giao; mãi đến lô `CAP-MG-0080` ngày `2026-05-11`, nguồn mới cập nhật `TODATE = 2026-05-03` cho `AUTOID 26..28` hoặc điều chỉnh lại).
- Bản ghi mới `AUTOID 216, 217, 218`: giao cho **`BRK021`**, `FRDATE = 2026-05-04`, `TODATE = 9999-12-31` (từ lô `CAP-MG-0080` ngày `11/05` sửa `TODATE = 2026-05-08`).

### Các phương án cân nhắc & So sánh số liệu tại ngày `2026-05-05` (`P-MG-OVERLAP`)

Tại ngày `2026-05-05` (lô `ref_nav` `CAP-MG-0059`), NAV của 3 tiểu khoản chồng lấn là:

- `9994000026`: `1.640.000.000` VND
- `9994000027`: `760.000.000` VND
- `9994000028`: `2.050.000.000` VND
- **Tổng NAV của 3 tiểu khoản chồng lấn ngày `05/05`:** **`4.450.000.000` VND**.

| Phương án                                                                                                                                              | Quy tắc phân xử                                                                                                                                                                                                                                                                          | Hệ quả tại ngày `2026-05-05` (`P-MG-OVERLAP`)                                                                                                                                                                                                                                                                                                                                                             |
| ------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Phương án A (ĐƯỢC CHỌN):** Phân công có **`FRDATE` muộn hơn thắng** (nếu cùng `FRDATE` thì `ingested_ts` muộn hơn / `AUTOID` lớn hơn thắng, so như số khi toàn chữ số) | Khi một tiểu khoản có nhiều phân công `STATUS = 'A'` thỏa `FRDATE <= D <= TODATE`, xếp hạng `ROW_NUMBER() OVER (PARTITION BY afacctno ORDER BY frdate DESC, ingested_ts DESC, autoid::bigint DESC) = 1`. Gắn cờ `is_overlap_resolved = true`, `resolution_basis = 'DEC-CAP-MG-OVERLAP'`. | - Tiểu khoản `9994000026..28` ngày `05/05` thuộc về **`BRK021`**.- `CAP-MG-BOOKNAV` ngày `05/05` của **`BRK021`** tăng thêm `4.450.000.000` VND (từ `8.910.000.000` của 8 TK gốc lên **`13.360.000.000`** với 11 TK).- `CAP-MG-BOOKNAV` ngày `05/05` của **`BRK010`** chỉ gồm 5 TK còn lại (`9994000021..25`) = **`6.160.000.000`** VND.- Đảm bảo bất biến `C-SA-ONEBROKER` (`TC-CAP-MG-ONEBROKER` xanh). |
| **Phương án B:** Phân công cũ (`FRDATE` sớm hơn / `AUTOID` nhỏ hơn) thắng                                                                              | Ưu tiên bản ghi gốc cho đến khi bản ghi gốc chính thức đóng `TODATE`.                                                                                                                                                                                                                    | - Tiểu khoản `9994000026..28` ngày `05/05` vẫn tính cho **`BRK010`**.- `CAP-MG-BOOKNAV` ngày `05/05` của **`BRK010`** = `6.160.000.000 + 4.450.000.000` = **`10.610.000.000`** VND (8 TK); của **`BRK021`** = **`8.910.000.000`** VND (8 TK).- Trái với thực tế nghiệp vụ là phân công mới sinh ra để thay thế phân công cũ nhưng tác nghiệp viên quên đóng ngày kết thúc của dòng cũ.                    |
| **Phương án C:** Giữ cả hai môi giới và cảnh báo                                                                                                       | Không khử trùng trên Business Vault, cho phép 1 tiểu khoản gắn với 2 môi giới cùng ngày.                                                                                                                                                                                                 | - Vi phạm trực tiếp ràng buộc `C-SA-ONEBROKER` (làm test `TC-CAP-MG-ONEBROKER` đỏ) và làm tổng `BOOKNAV` toàn công ty/chi nhánh bị tính trùng tăng ảo `4.450.000.000` VND.                                                                                                                                                                                                                                |

### Quyết định chốt

Chọn **Phương án A**: Ưu tiên bản ghi phân công có **`FRDATE` muộn hơn thắng** (tie-breaker: `ingested_ts DESC`, rồi `autoid` giảm dần: so như số nếu toàn chữ số, ngược lại so chữ, vì nguồn không đảm bảo `AUTOID` là số), gắn cờ `is_overlap = true` và `care_basis` chứa `DEC-CAP-MG-OVERLAP` ở `mart.dim_account_care_daily`, đồng thời ghi nhận 3 tiểu khoản chồng lấn vào bảng báo cáo chất lượng `mart.dq_mg_daily` với mã `DQ-CHONGLAN` (`ASSIGNMENT_OVERLAP`, `QUYETDINH`).

---

## 3. `DEC-CAP-MG-GAP` — Môi giới đã nghỉ việc mà tiểu khoản chưa chuyển (`TH-NGHIVIEC`): Hiển thị ai?

### Bối cảnh & Dữ liệu thực tế

- Môi giới `BRK017` (Ngô Đức Châu) nghỉ việc với `LEAVEDATE = 2026-04-30`, nhưng thông tin nghỉ việc này chỉ được hệ thống nguồn cập nhật từ lô `CAP-MG-0052` (`2026-05-04`), cùng thời điểm 12 tiểu khoản `9994000109..9994000120` được chuyển sang `BRK018` (`FRDATE = 2026-05-04`).
- Trong trường hợp tổng quát (hoặc tại các ngày nghỉ lễ `01/05`–`03/05` khi xét lịch sử hiệu lực nhân sự, hoặc khi môi giới đã có `STATUS = 'C'` / `LEAVEDATE < D` nhưng bản ghi `flex_reaflnk` vẫn còn hiệu lực `FRDATE <= D <= TODATE`), hệ thống cần quy tắc hiển thị người chăm sóc trên `gold.dim_account_care_daily`.

### Các phương án cân nhắc

| Phương án                                                                                                                           | Mô tả xử lý                                                                                                                                                         | Hệ quả lên `gold.dim_account_care_daily` và chỉ số `KH-ORPHANCNT` (`FNV-MET-001 §7.8`)                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ----------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Phương án A (ĐƯỢC CHỌN):** **Giữ nguyên môi giới đang được phân công (người đã nghỉ) kèm cờ cảnh báo `is_carer_inactive = true`** | Tuân thủ đúng yêu cầu tại Bảng 68 (`TH-NGHIVIEC`: _"Trong khoảng trống, tiểu khoản vẫn gắn người đã nghỉ, có cờ"_). Không tự ý sửa dữ liệu phân công của Core FLEX. | - `dim_account_care_daily` vẫn hiển thị `broker_key` của môi giới trên hợp đồng phân công, nhưng có cờ `is_carer_inactive = true` và `care_basis` chứa `DEC-CAP-MG-GAP`.- Khi tính chỉ số tiểu khoản mồ côi / thiếu người chăm sóc hoạt động (`KH-ORPHANCNT`), các tiểu khoản có `broker_key IS NULL OR is_carer_inactive = true` đều được đếm vào diện cần tái phân công, giúp phòng Kinh doanh phát hiện ngay các tiểu khoản đang gắn với nhân viên đã nghỉ việc. |
| **Phương án B:** Tự động gán về Trưởng nhóm (`LEAD-G*`)                                                                             | Khi môi giới có `STATUS = 'C'`, tự động đẩy tiểu khoản lên cho Trưởng nhóm quản lý.                                                                                 | - Làm sai lệch lịch sử phân công thực tế của hệ thống Core FLEX và làm chỉ số `KH-ORPHANCNT` bằng `0` (che giấu việc tiểu khoản chưa được tái phân công chính thức).                                                                                                                                                                                                                                                                                                                                         |
| **Phương án C:** Để trống (`broker_key = NULL`)                                                                                     | Xóa trắng người chăm sóc ngay khi môi giới nghỉ việc.                                                                                                               | - Làm mất dấu vết lịch sử tiểu khoản đó từng thuộc về nhóm/chi nhánh nào trong khoảng trống chuyển giao, gây lệch số cộng dồn cấp nhóm/chi nhánh (`TC-CAP-MG-ROLLUP`).                                                                                                                                                                                                                                                                                                                                       |

### Quyết định chốt

Chọn **Phương án A**: Giữ môi giới được phân công theo `flex_reaflnk`, gắn cờ `is_carer_inactive = true` (`care_basis` chứa `DEC-CAP-MG-GAP`, `mart.dim_account_care_daily`) khi người mang mã tại `D` có `STATUS = 'C'` hoặc `D > LEAVEDATE` (`work_status = 'LEFT'` ở `mart.dim_broker_org_daily`). Dữ liệu đề: khoảng trống `01–03/05` của `BRK017` không có ngày giao dịch nào, nên Gold không có dòng mang cờ này; quy tắc vẫn chạy cho mọi ngày.

---

## 4. `DEC-CAP-MG-CYCLE` — Cây đơn vị có vòng (`DQ-VONG`): Dựng cây ngày đó thế nào?

### Bối cảnh & Dữ liệu thực tế

Tại lô `CAP-MG-0061` (`business_date = 2026-05-06`), bảng `flex_regrp` có 2 dòng tạo chu trình trực tiếp:

- `GRPID = 'G5'` có `PARENTID = 'G6'`
- `GRPID = 'G6'` có `PARENTID = 'G5'`
  (Trong khi ở các lô trước đó từ `17/04` đến `05/05`, cả `G5` và `G6` đều có `PARENTID = 'CN3'`; và sang lô `CAP-MG-0066` ngày `07/05`, nguồn đã sửa lại `G5 -> CN3`, `G6 -> CN3`).

### Các phương án cân nhắc

| Phương án                                                                                                                                                              | Mô tả thiết kế                                                                                                                                                                                                                                                                                                                                                                                                                   | Hệ quả tại ngày `2026-05-06` (`P-MG-CYCLE` & `TC-CAP-MG-ROLLUP`)                                                                                                                                                                                                                                                                                                                                                            |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Phương án A (ĐƯỢC CHỌN):** **Loại các dòng tạo vòng tại Staging (`CYCLE_DETECTED`) và giữ nguyên phiên bản cha hợp lệ liền trước (`CN3`) khi dựng cây ngày `06/05`** | - Tại `stg_flex__regrp`, thuật toán phát hiện chu trình đẩy 2 dòng lỗi `G5` và `G6` của lô `CAP-MG-0061` sang `stg_flex__regrp__rejected` với `reason_code = 'CYCLE_DETECTED'`.- Nhờ 2 dòng lỗi không vào Raw Vault (hoặc bị chặn ở Business Vault), khi dựng `bridge_regrp_ancestor` tại `as-of 2026-05-06`, phiên bản hiệu lực mới nhất của `G5` và `G6` trong Satellite vẫn là phiên bản hợp lệ từ lô trước (`PARENTID = 'CN3'`). | - Đúng hoàn toàn với yêu cầu tại Bảng 67 (`DQ-VONG`: _"LOAI các dòng tạo vòng; giữ phiên bản cây trước đó"_).- Tại ngày `06/05` (`P-MG-CYCLE`), đơn vị cha của `G5` và `G6` là **`CN3`**, đường dẫn cây là `HO > CN3 > G5` và `HO > CN3 > G6`.- Mọi nút đều có đường đi lên tới `HO` (`TC-CAP-MG-TREE` xanh) và tổng số tiểu khoản/NAV cấp chi nhánh `CN3` bằng đúng tổng các nhóm con `G5 + G6` (`TC-CAP-MG-ROLLUP` xanh). |
| **Phương án B:** Bỏ hẳn các nút tạo vòng (`G5`, `G6`) khỏi cây ngày `06/05`                                                                                            | Không dùng phiên bản trước, xóa `G5` và `G6` khỏi cây tổ chức ngày `06/05`.                                                                                                                                                                                                                                                                                                                                                      | - Toàn bộ 8 môi giới thuộc nhóm `G5` và `G6` bị mất đơn vị vào ngày `06/05`, làm sụt giảm đột ngột số liệu cộng dồn của Chi nhánh 3 (`CN3`) và Hội sở (`HO`) vào ngày `06/05`.                                                                                                                                                                                                                                              |
| **Phương án C:** Dừng pipeline (`STOP build`)                                                                                                                          | Báo lỗi và dừng toàn bộ tiến trình chạy ngày `06/05`.                                                                                                                                                                                                                                                                                                                                                                            | - Vi phạm nguyên tắc Cô lập lỗi (`QT-COLAP`): dữ liệu lỗi ở 2 dòng của 1 lô làm tê liệt báo cáo toàn hệ thống.                                                                                                                                                                                                                                                                                                              |

### Quyết định chốt

Chọn **Phương án A**: Phát hiện chu trình trên từng lô `flex_regrp` tại tầng Staging, đưa các dòng thuộc chu trình (`G5`, `G6` ở lô `CAP-MG-0061`) vào `stg_flex__regrp__rejected` với `reason_code = 'CYCLE_DETECTED'`. Tầng Business Vault (`bridge_regrp_ancestor`) ngày `2026-05-06` kế thừa trạng thái hợp lệ liền trước (`G5 -> CN3`, `G6 -> CN3`).

---

## 5. `DEC-CAP-MG-STAGING-RULES` — Xử lý Ô lỗi công thức Excel (`DQ-CONGTHUC`) và Thứ tự ưu tiên khi một dòng mắc nhiều lỗi cùng lúc

### 5.1. Xử lý `DQ-CONGTHUC` trên bảng `manual_kpi` (Loại ô hay Loại dòng?)

- **Bối cảnh:** Tại cả 2 lô `CAP-MG-0103` (`v1.xlsx`) và `CAP-MG-0104` (`v2.xlsx`), dòng Excel số 22 (`broker_id = 'BRK021'`, Hồ Xuân Khánh) có ô `target_calls = '#REF!'`. Bảng 67 yêu cầu: _"LOAI ô hoặc dòng, ghi rõ trong D-QUYETDINH"_.
- **Các phương án:**
  - _Phương án 1 (Loại ô - thay `'#REF!'` bằng `NULL`):_ Giữ dòng của `BRK021` trong `stg_manual__kpi` với `target_calls = NULL`. Nhược điểm: Cột `target_calls` là chỉ tiêu bắt buộc để tính tỷ lệ hoàn thành cuộc gọi quý trên `gold.met_broker_daily`; để `NULL` làm mất mẫu số KPI và trái với test `TC-CAP-MG-EXCEL` (_"ô lỗi và dòng chưa duyệt bị loại"_).
  - _Phương án 2 (ĐƯỢC CHỌN — Loại cả dòng):_ Đưa toàn bộ dòng có chứa bất kỳ ô lỗi công thức Excel nào (`#REF!`, `#DIV/0!`, `#VALUE!`, `#NAME?`, `#N/A`) sang view `stg_manual__kpi__rejected` với `reason_code = 'FORMULA_ERROR'`.
- **Hệ quả định lượng (`P-MG-KPI`):** Trong mỗi file `manual_kpi` (23 dòng dữ liệu), có **4 dòng bị loại** sang `stg_manual__kpi__rejected`: 3 dòng do `UNAPPROVED_ROW` (`BRK012`, `BRK013`, `BRK014`) và 1 dòng do `FORMULA_ERROR` (`BRK021`), còn lại **19 dòng hợp lệ** đi vào `stg_manual__kpi`.

### 5.2. Thứ tự ưu tiên phân loại khi một dòng vi phạm nhiều lỗi cùng lúc (Multi-Defect Precedence Waterfall)

Để đảm bảo bất biến đối soát **`GT-STG-RECON` (`rows_landing = rows_valid + rows_rejected`)**, mỗi dòng trong `landing` chỉ được phép đi vào `stg_*` **HOẶC** xuất hiện **đúng 1 lần** trong `stg_*__rejected` với một mã `reason_code` duy nhất. Khi một bản ghi vi phạm nhiều điều kiện cùng lúc, hệ thống đánh giá theo biểu thức `CASE WHEN` đơn định theo thứ tự ưu tiên từ cao xuống thấp:

1. **Ưu tiên 1 — `FORMULA_ERROR` (`DQ-CONGTHUC`):** Ô dữ liệu chứa chuỗi lỗi công thức bảng tính (`^#(REF!|DIV/0!|VALUE!|NAME\?|N/A|NUM!|NULL!)$`).
2. **Ưu tiên 2 — `KEY_NULL` (`DQ-KHOA-NULL`):** Cột thuộc khóa nghiệp vụ (`business_key`) hoặc cột định danh bắt buộc (`broker_id`, `afacctno`, `REACCTNO`) bị `NULL` hoặc chuỗi rỗng sau khi `trim`.
3. **Ưu tiên 3 — `KEY_FORMAT` / `INVALID_NUMERIC`:** Giá trị khóa hoặc cột số/ngày bắt buộc không khớp biểu thức định dạng (`formats`) trong Hợp đồng nguồn.
4. **Ưu tiên 4 — `ALLCODE_UNKNOWN` (`DQ-MA-LA`):** Giá trị cột danh mục không tồn tại trong bảng tham chiếu chuẩn (`ref/event_type.csv` hoặc danh mục trạng thái).
5. **Ưu tiên 5 — Ràng buộc Nghiệp vụ & Toàn vẹn cấu trúc (`INVALID_DATE_RANGE` / `UNAPPROVED_ROW` / `CYCLE_DETECTED`):**
   - `FRDATE > TODATE` (`DQ-NGAY-SAI` $\rightarrow$ `INVALID_DATE_RANGE`).
   - Thiếu `approver` hoặc `approved_date` (`DQ-CHUADUYET` $\rightarrow$ `UNAPPROVED_ROW`).
   - Cạnh đồ thị tạo chu trình khép kín (`DQ-VONG` $\rightarrow$ `CYCLE_DETECTED`).
6. **Ưu tiên 6 — Xung đột / Trùng lặp bản ghi trong lô (`CONFLICT_IN_BATCH` / `DUPLICATE_EVENT`):**
   - Với bảng snapshot: cùng `business_key` xuất hiện $\ge 2$ lần trong một lô với thuộc tính khác nhau (`CONFLICT_IN_BATCH`).
   - Với bảng sự kiện `finova_app_events` (`DQ-TRUNG-NGUYEN`): bản ghi trùng `event_id` (lấy `row_number() > 1` theo thứ tự xuất hiện) được tách sang `stg_finova_app__events__rejected` với `reason_code = 'CONFLICT_IN_BATCH'` (hoặc `DUPLICATE_EVENT`) để vừa khử trùng ở view chính (`634` dòng hợp lệ), vừa bảo toàn tổng đối soát `rows_landing (653) = rows_valid (634) + rows_rejected (19)` cho `GT-STG-RECON`.
7. **Ưu tiên 7 — Sửa tự động (`SUA`) và Cảnh báo (`CANHBAO`) trên các dòng hợp lệ:**
   - Chỉ khi bản ghi vượt qua cả 6 bước kiểm tra loại dòng trên, tầng Staging mới áp dụng quy tắc sửa tự động (`DQ-TUONGLAI`: khi `event_ts > server_ts + interval '5 minutes'` thì lấy `server_ts` và đặt `is_future_ts_fixed = true`; `DQ-EXCEL`: đổi dấu phẩy thập phân thành dấu chấm) và chuyển tiếp vào Raw Vault.

---

## 6. `DEC-CAP-MG-ORPHAN` — Đơn vị trỏ tới đơn vị cha không tồn tại (`DQ-MOCOI`): có đưa vào cây ngày D không?

### Bối cảnh & Dữ liệu thực tế

Bảng 67 xếp `DQ-MOCOI` là `CANHBAO`: nhận dòng, cảnh báo (test warn `test_stg_regrp_parent_missing` ở staging). Nhưng `TC-CAP-MG-TREE` (Bảng 70) yêu cầu mọi nút trong cây ngày D có đường đi lên tới `HO`. Dữ liệu đề: `G7` có `PARENTID = 'CN9'` ở hai lô `23/04` và `24/04`; `CN9` không có trong bản chụp nào. Từ `CAP-MG-0032` (`27/04`) `G7` vắng khỏi bản chụp (`sts_regrp__flex` DELETED). As-of `23/04` và `24/04`: `0` môi giới thuộc `G7`, `0` đơn vị con của `G7`.

### Các phương án cân nhắc

Nhánh mồ côi: đơn vị có cha không tồn tại trong cây của D cùng mọi đơn vị dưới nó. Phân hai dạng theo việc nhánh có môi giới nào tại D:

- **Không có số liệu** (như `G7` của đề): đơn vị không có thật, bản sau sửa ngay. Bỏ hay giữ đều không đổi số liệu.
- **Có số liệu**: nguồn sai mapping cha nên số của môi giới, tiểu khoản trong nhánh không lên được `HO`; nguồn sửa thì nối lại ngay.

| Phương án | Mô tả | Hệ quả |
|---|---|---|
| A (bản trước, bị thay): Bỏ mọi nhánh mồ côi khỏi cây ngày D | Chuỗi dừng không ở gốc, không vì vòng thì bỏ cả chuỗi | `G7`: cây `10` đơn vị, `TC-CAP-MG-TREE` xanh. Nhánh có số liệu thì mất số khỏi mọi cấp, tổng `HO` nhỏ hơn tổng công ty; trái `CANHBAO` (nhận dòng) của Bảng 67. Test xanh chỉ vì `G7` không có môi giới |
| B: Giữ đơn vị mồ côi làm gốc riêng | Bridge giữ `G7` với cấp trên duy nhất là chính nó | `TC-CAP-MG-TREE` đỏ (`G7` không lên được `HO`, hai gốc) |
| C: Gắn đơn vị mồ côi vào thẳng gốc `HO` | Tự tạo cạnh `G7 -> HO` | Test xanh nhưng bịa ra quan hệ nguồn không có; số của nhánh cộng thẳng vào `HO`, không phân biệt được với số thật |
| **D (ĐƯỢC CHỌN):** Bỏ nhánh không có số liệu; nhánh có số liệu treo vào nút ảo `UNKNOWN` dưới gốc | Đơn vị đứng đầu nhánh có cấp trên là `UNKNOWN`, `UNKNOWN` có cấp trên là gốc; cờ `is_orphan_branch`. Quy tắc chung, không nêu tên đơn vị | `G7` (không số liệu): cây `10` đơn vị như A. Nhánh có số liệu: không mất số, tổng `HO` đủ; `TC-CAP-MG-TREE` xanh (mọi nút lên được gốc, một gốc); Gold hiện nhánh "Chưa xác định" để nghiệp vụ thấy lỗi nguồn |

### Quyết định chốt

Chọn **Phương án D**. "Có số liệu" là có môi giới tại D (hồ sơ as-of, `grpid` thuộc nhánh); tiểu khoản, NAV, sự kiện đều gắn qua môi giới. Ngày có bản sửa cha ≤ cutoff tự nối về cha thật; ngày trước đó giữ `UNKNOWN` (INV-SEM-ASOF, không dựng lại lịch sử). Dòng mồ côi vẫn nằm trong raw vault, mã cha thiếu đọc ở `parentid`, cảnh báo vẫn ở `test_stg_regrp_parent_missing`. Vòng (`DQ-VONG`) không áp quy tắc này: bridge giữ đơn vị nằm trên vòng để `TC-CAP-MG-TREE` đỏ (phép thử âm "nạp cây có vòng, không lọc"), còn xử lý vòng theo `DEC-CAP-MG-CYCLE` ở staging. Chi tiết và kiểm tình huống có số liệu: `docs/ky_thuat_asof_bv.md` AB-06.

---

## 7. `DEC-CAP-MG-RLSROLE` — RLS của Gold (`INV-SEM-RLSDB`, `TC-CAP-MG-RLS`): policy áp cho role nào?

### Bối cảnh

`INV-SEM-RLSDB`: lọc dữ liệu theo môi giới do policy RLS của database thực hiện, không do tầng ứng dụng. Mục 2.2 và Bảng 13 có hai role `NOLOGIN`: `finova_loader` (không có quyền vào `mart`) và `finova_dbt` (dựng và là chủ bảng Gold). PostgreSQL không áp RLS cho chủ bảng, trừ khi bật `force row level security`.

### Các phương án cân nhắc

| Phương án | Mô tả | Hệ quả (as-of `15/05`, 200 tiểu khoản) |
|---|---|---|
| **A (ĐƯỢC CHỌN):** Thêm role đọc `finova_app` `NOLOGIN`, chỉ `USAGE` trên `mart` và `SELECT` trên 4 bảng của Bảng 71 | Policy `for select to finova_app`; người xem đặt `finova.viewer_id`. `finova_dbt` vẫn là chủ bảng, không bị lọc | Không đặt người xem, hoặc người xem không có trong `org_roles`: thấy `0` dòng. `finova_app` không ghi, không xóa được, không đọc được `atomic`, `staging`. Lệch đề: thêm một role ngoài Bảng 13 (`check_khung.py` chỉ kiểm hai role chức năng tồn tại, đúng quyền) |
| B: Giữ hai role, `force row level security` trên `finova_dbt` | Policy phải cho phiên chưa đặt người xem thấy hết, để `asof_day_delete` xóa được ngày D và test dbt (grain, tổng khớp vault, ROLLUP) đọc được dữ liệu | Không thêm role, nhưng mọi phiên `finova_dbt` bỏ trống `finova.viewer_id` thấy cả `200/200` tiểu khoản, và có quyền ghi, xóa. Việc lọc thực chất phụ thuộc ứng dụng có đặt người xem hay không, trái `INV-SEM-RLSDB` |

### Quyết định chốt

Chọn **Phương án A**. Role `finova_app` khai ở `setup/bootstrap.sql` mục 6, tên ở `var('gold_reader_role')`. Policy:

- `sec_visibility_daily`: `viewer_id = finova.viewer_id`;
- `dim_account_care_daily`: có dòng của người xem trong `sec_visibility_daily` cùng ngày, cùng tiểu khoản;
- `dim_broker_org_daily`: `scope_ids` (mã môi giới, mọi đơn vị trên đường dẫn cây của D) giao với phạm vi của người xem trong `org_roles` (hàm `mart.viewer_scopes()`, `security definer` để role đọc không cần quyền trên `staging`);
- `met_broker_daily`: người xem thấy môi giới đó ở `dim_broker_org_daily`.

`dq_mg_daily` không cấp cho role đọc. Bằng chứng: `tests/gold/test_rls.py` (5 test xanh); phép thử âm "cho `BRK003` xem tiểu khoản của `BRK009`" đỏ ở `11/05`.

---

## 8. `DEC-CAP-MG-INTER30` — Tương tác `DQ-QUYEN` có tính vào "số tương tác 30 ngày" không?

### Bối cảnh

Bảng 67: `DQ-QUYEN` (môi giới ghi tương tác với tiểu khoản không do mình chăm sóc tại thời điểm đó) là `CANHBAO; không tính vào độ phủ`. Bảng 71 có thêm cột "số tương tác 30 ngày" nhưng Bảng 72 không định nghĩa riêng. Dữ liệu đề: 7 tương tác `DQ-QUYEN` theo phân công hệ thống biết tại cutoff của ngày nạp: `BRK005` 2 (`06/05`), `BRK009` 5 (`13/05`).

### Các phương án cân nhắc

| Phương án | Mô tả | Hệ quả as-of `15/05` |
|---|---|---|
| **A (ĐƯỢC CHỌN):** Tính mọi tương tác hợp lệ của người mang mã; chỉ loại `DQ-QUYEN` khỏi tử của `CAP-MG-COVER30` | Đúng chữ của Bảng 67: chỉ loại khỏi độ phủ | `interactions_30d`: `BRK009` = `40`, `BRK005` = `31`. `CAP-MG-COVER30` của `BRK009` = `16/22` (không đổi giữa hai phương án) |
| B: Loại `DQ-QUYEN` khỏi cả số tương tác | Coi tương tác sai quyền là không hợp lệ | `BRK009` = `35`, `BRK005` = `29`. Mở rộng quy tắc của đề sang cột đề không nói |

### Quyết định chốt

Chọn **Phương án A**. `DQ-QUYEN` vẫn được đếm và báo ở `dq_mg_daily` (`EVENT_NOT_ASSIGNED`, `CANHBAO`). "Ngày môi giới đang được giao tiểu khoản" trong tử của `CAP-MG-COVER30` xét theo bản phân công hệ thống biết tại cutoff(D) (`asof.sat_reaflnk__flex`), giữ đúng `INV-SEM-ASOF`.
