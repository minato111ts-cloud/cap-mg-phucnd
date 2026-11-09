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
| **A (ĐƯỢC CHỌN): mã nguồn làm khóa hub, tách người bằng satellite** | `broker_hk = dv_hash('FLEX', BROKERID)` ở **mọi** staging. `JOINDATE` nằm trong hashdiff của satellite hồ sơ môi giới: cấp lại mã thì sinh phiên bản mới. Business Vault dựng khoảng làm việc `[JOINDATE, LEAVEDATE]` của người mang mã tại `D`; Gold chỉ tính phân công và tương tác nằm trong khoảng làm việc đó. `broker_key = BROKERID:JOINDATE` suy từ phiên bản hiệu lực tại `D`. | 0 tiểu khoản, `CAP-MG-BOOKNAV = 0`, 0 tương tác 30 ngày. Nếu Gold quên lọc theo khoảng làm việc: vẫn 0 tiểu khoản nhưng **16 tương tác** (sai, của người cũ) vì cửa sổ 30 ngày tới `12/05` hay `15/05` đều phủ `20–29/04`. Test bảo vệ: `test_dec_brokerkey_new_holder_has_no_old_interactions` (`tests/gold/test_care_metrics.py`); bỏ lọc khoảng làm việc thì test đỏ với 16 tương tác. |
| **B: khóa ghép `(BROKERID, JOINDATE)`** | Hub là người. `flex_reaflnk` tra `JOINDATE` từ `flex_broker` ở staging; sự kiện và chỉ tiêu (khác nguồn) chỉ mang mã nên phải tra ở Business Vault, raw vault cần thêm hub theo mã và link nối hai hub. | Kết quả đúng như A nếu phép tra đúng. Tra theo `FRDATE` (người có `JOINDATE ≤ FRDATE`) **không ra người cho 4 phân công bẫy** của `BRK017`; tra theo người mang mã tại `ingested_ts` của lô buộc staging đọc landing `flex_broker` ngoài cửa sổ `(lo, hi]`, phụ thuộc thứ tự lô broker/reaflnk trong ngày và có rủi ro lệch giữa chạy theo ngày với full refresh (`PT-FULL`). |

### Quyết định chốt

Chọn **Phương án A**. Lý do:

1. Khóa hub là thứ cả bốn nguồn đều gửi, nên mọi link khớp hub mà không cần tra (`DEC-ELT-HUBSRC`, `GT-LNK-PARENT`). Test `tests/staging/test_stg_broker_hk_consistent.sql` chặn việc các staging tính `broker_hk` khác nhau.
2. Logic tách người chỉ nằm ở **một** chỗ (Business Vault/Gold, dựa trên phiên bản satellite đã lọc as-of), thay vì rải ở staging và Business Vault như B. Dù chọn phương án nào, sự kiện ứng dụng chỉ mang mã nên logic khoảng làm việc vẫn bắt buộc phải có.
3. Đối chiếu `DEC-SA-BROKERKEY` (chưa chốt): đề xuất của Finova khóa hub bằng `RECFLNK.AUTOID`, giữ `REACCTNO` làm khóa phụ thuộc trên link chăm sóc, và cảnh báo có thể cần "một khóa người ổn định". Gói đề không có `RECFLNK`, nên hub ở đây khóa theo mã `BROKERID`, tức lệch đề xuất. Tinh thần giữ nguyên: mã quen dùng vẫn tra được, và `broker_key = BROKERID:JOINDATE` ở Business Vault/Gold chính là khóa người ổn định đó.

Hệ quả lên số liệu trước ngày cấp lại: không đổi. Người cũ giữ `broker_key = BRK017:2025-05-14`, tại `29/04` có 13 tiểu khoản, `CAP-MG-BOOKNAV = 22.129.625.000`, 16 tương tác; từ `04/05` tới `08/05` có 0 tiểu khoản, 16 tương tác. Từ `11/05` mã thuộc `BRK017:2026-05-11` với 0 tiểu khoản, 0 tương tác.

Chỉ tiêu nhập tay (`manual_kpi`) cũng chỉ mang mã. Gold chỉ áp chỉ tiêu khi `approved_date` nằm trong khoảng làm việc của người mang mã tại `D`; ngoài khoảng thì `kpi_target_calls` NULL và `dq_mg_daily` gắn cờ `KPI_NOT_FOR_HOLDER` để nghiệp vụ duyệt lại. So `approved_date` chứ không so `ingested_ts`, vì file chỉ tiêu là bản chụp đầy đủ: bản sau có thể chép nguyên dòng duyệt cho người cũ. Khoảng làm việc của tương tác và chỉ tiêu dùng chung macro `gold_in_tenure`. Gói đề không có dòng chỉ tiêu `BRK017` nên số liệu không đổi; ca bị chặn thử bằng `ut_met_kpi_not_for_new_holder` và `ut_dq_kpi_not_for_holder_on_reuse_batch`. Đánh đổi: chỉ tiêu duyệt trước cho người sắp nhận mã (duyệt trước `JOINDATE`) cũng bị chặn và chờ nghiệp vụ xác nhận, không tự gán.

Đánh đổi chấp nhận: raw vault không tự phân biệt hai người của cùng mã; nếu Gold quên lọc theo khoảng làm việc thì số liệu của người mới bị lẫn người cũ (16 tương tác ở ví dụ trên). Người cũ biến khỏi bản chụp từ `11/05` thể hiện bằng phiên bản satellite mới, không phải bằng việc khóa hub vắng mặt.

---

## 2. `DEC-CAP-MG-OVERLAP` — Hai môi giới cùng hiệu lực trên một tiểu khoản (`DQ-CHONGLAN`): Tính cho ai?

### Bối cảnh & Dữ liệu thực tế

Từ lô `CAP-MG-0053` (`04/05`), **3 tiểu khoản (`9994000026`, `9994000027`, `9994000028`)** có 2 bản ghi phân công cùng thỏa `FRDATE <= D <= TODATE`:

- `AUTOID 26, 27, 28`: giao cho **`BRK010`**, `FRDATE` năm `2025`, `TODATE = 9999-12-31`. Nguồn không đóng dòng này ở bất kỳ lô nào.
- `AUTOID 216, 217, 218`: giao cho **`BRK021`**, `FRDATE = 2026-05-04`, `TODATE = 9999-12-31`. Lô `CAP-MG-0080` (`11/05`) đóng về `TODATE = 2026-05-08`.

Hệ quả theo as-of: `04/05` tới `08/05` có chồng lấn (5 ngày giao dịch), phương án chọn cho `BRK021`. Từ as-of `11/05`, `AUTOID 216..218` đã đóng nên tiểu khoản về `BRK010`, không còn chồng lấn tại `D`. Việc nguồn giữ `BRK021` tới `08/05` phù hợp với phương án được chọn cho các ngày đó.

### Các phương án cân nhắc & So sánh số liệu tại ngày `2026-05-05` (`P-MG-OVERLAP`)

NAV ngày `05/05` (`ref_nav`, số đủ đồng):

- `9994000026`: `2.781.711.000`
- `9994000027`: `2.774.697.000`
- `9994000028`: `2.214.312.000`
- **Tổng 3 tiểu khoản chồng lấn:** **`7.770.720.000`**

Phần không tranh chấp: `BRK010` 9 tiểu khoản `16.244.048.000`; `BRK021` 7 tiểu khoản `7.344.038.000`.

| Phương án | Quy tắc | Môi giới của `9994000026` | `CAP-MG-BOOKNAV` `BRK010` (số TK) | `CAP-MG-BOOKNAV` `BRK021` (số TK) | Nhận xét |
| --- | --- | --- | ---: | ---: | --- |
| **A (ĐƯỢC CHỌN): `FRDATE` muộn hơn thắng** | Xếp `frdate desc`, rồi `ingested_ts desc`, rồi `autoid` giảm dần | `BRK021` | `16.244.048.000` (9) | `15.114.758.000` (10) | Đúng số ở `mart.met_broker_daily`. `TC-CAP-MG-ONEBROKER` xanh |
| B: Phân công biết sau thắng | Xếp `ingested_ts desc` | `BRK021` | `16.244.048.000` (9) | `15.114.758.000` (10) | Cùng số với A trên dữ liệu đề, vì `AUTOID 216..218` vừa có `FRDATE` muộn hơn vừa biết sau. Lệch A khi nguồn nhập bù một phân công cũ hơn (`TH-LUIHIEULUC`): phân công đó thắng dù hiệu lực sớm hơn |
| C: Phân công cũ thắng | Xếp `frdate asc` | `BRK010` | `24.014.768.000` (12) | `7.344.038.000` (7) | Ngược nghiệp vụ: phân công mới sinh ra để thay phân công cũ, nguồn quên đóng dòng cũ |
| D: Tính cho cả hai và báo | Không phân xử | Cả hai | `24.014.768.000` (12) | `15.114.758.000` (10) | Tổng hai môi giới thừa `7.770.720.000`, tổng chi nhánh và công ty bị tính trùng; vi phạm `C-SA-ONEBROKER`, `TC-CAP-MG-ONEBROKER` đỏ |

### Quyết định chốt

Chọn **Phương án A**: Ưu tiên bản ghi phân công có **`FRDATE` muộn hơn thắng** (tie-breaker: `ingested_ts DESC`, rồi `autoid` giảm dần: so như số nếu toàn chữ số, ngược lại so chữ, vì nguồn không đảm bảo `AUTOID` là số), gắn cờ `is_overlap = true` và `care_basis` chứa `DEC-CAP-MG-OVERLAP` ở `mart.dim_account_care_daily`, đồng thời ghi nhận 3 tiểu khoản chồng lấn vào bảng báo cáo chất lượng `mart.dq_mg_daily` với mã `DQ-CHONGLAN` (`ASSIGNMENT_OVERLAP`, `QUYETDINH`).

---

## 3. `DEC-CAP-MG-GAP` — Môi giới đã nghỉ việc mà tiểu khoản chưa chuyển (`TH-NGHIVIEC`): Hiển thị ai?

### Bối cảnh & Dữ liệu thực tế

- Môi giới `BRK017` (Ngô Đức Châu) nghỉ việc với `LEAVEDATE = 2026-04-30`, nhưng thông tin nghỉ việc này chỉ được hệ thống nguồn cập nhật từ lô `CAP-MG-0052` (`2026-05-04`), cùng thời điểm 13 tiểu khoản (`9994000020..25`, `9994000041`, `065`, `089`, `113`, `137`, `161`, `185`) đóng ở `03/05` và chuyển sang `BRK018` (`FRDATE = 2026-05-04`).
- Trong trường hợp tổng quát (hoặc tại các ngày nghỉ lễ `01/05`–`03/05` khi xét lịch sử hiệu lực nhân sự, hoặc khi môi giới đã có `STATUS = 'C'` / `LEAVEDATE < D` nhưng bản ghi `flex_reaflnk` vẫn còn hiệu lực `FRDATE <= D <= TODATE`), hệ thống cần quy tắc hiển thị người chăm sóc trên `gold.dim_account_care_daily`.

### Các phương án cân nhắc

| Phương án                                                                                                                           | Mô tả xử lý                                                                                                                                                         | Hệ quả lên `gold.dim_account_care_daily` và chỉ số `KH-ORPHANCNT` (`FNV-MET-001 §7.8`)                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ----------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Phương án A (ĐƯỢC CHỌN):** **Giữ nguyên môi giới đang được phân công (người đã nghỉ) kèm cờ cảnh báo `is_carer_inactive = true`** | Tuân thủ đúng yêu cầu tại Bảng 68 (`TH-NGHIVIEC`: _"Trong khoảng trống, tiểu khoản vẫn gắn người đã nghỉ, có cờ"_). Không tự ý sửa dữ liệu phân công của Core FLEX. | - `dim_account_care_daily` vẫn hiển thị `broker_key` của môi giới trên hợp đồng phân công, nhưng có cờ `is_carer_inactive = true` và `care_basis` chứa `DEC-CAP-MG-GAP`.- Khi tính chỉ số tiểu khoản mồ côi / thiếu người chăm sóc hoạt động (`KH-ORPHANCNT`), các tiểu khoản có `broker_key IS NULL OR is_carer_inactive = true` đều được đếm vào diện cần tái phân công, giúp phòng Kinh doanh phát hiện ngay các tiểu khoản đang gắn với nhân viên đã nghỉ việc. |
| **Phương án B:** Tự động gán về Trưởng nhóm (`LEAD-G*`)                                                                             | Khi môi giới có `STATUS = 'C'`, tự động đẩy tiểu khoản lên cho Trưởng nhóm quản lý.                                                                                 | - Làm sai lệch lịch sử phân công thực tế của hệ thống Core FLEX và làm chỉ số `KH-ORPHANCNT` bằng `0` (che giấu việc tiểu khoản chưa được tái phân công chính thức).                                                                                                                                                                                                                                                                                                                                         |
| **Phương án C:** Để trống (`broker_key = NULL`)                                                                                     | Xóa trắng người chăm sóc ngay khi môi giới nghỉ việc.                                                                                                               | - Làm mất dấu vết lịch sử tiểu khoản đó từng thuộc về nhóm/chi nhánh nào trong khoảng trống chuyển giao, gây lệch số cộng dồn cấp nhóm/chi nhánh (`TC-CAP-MG-ROLLUP`).                                                                                                                                                                                                                                                                                                                                       |

### Số liệu theo từng phương án

`KH-ORPHANCNT` (FNV-MET-001 §7.8) đếm tiểu khoản không có liên kết môi giới hiệu lực hoặc môi giới đứng tên đã nghỉ. Trên Gold đọc bằng `count(*) filter (where broker_key is null or is_carer_inactive)`.

**Dữ liệu đề: `KH-ORPHANCNT = 0` ở cả 19 ngày giao dịch, cả ba phương án.** Ngày nghỉ của người cũ là `30/04`, nhưng `01–03/05` không có ngày giao dịch; ngày giao dịch `04/05` thì 13 tiểu khoản đã thuộc `BRK018`. As-of `29/04` hệ thống cũng chưa biết người này nghỉ. Ba phương án chỉ khác nhau khi có ngày giao dịch trong khoảng trống.

Để thấy số khác nhau, phép thử trên database thử giữ 13 tiểu khoản ở `BRK017` tới `05/05` (kéo dài `TODATE`, dời `FRDATE` của `BRK018`, dựng lại ngày `05/05`):

| Phương án | `KH-ORPHANCNT` tại `05/05` | `CAP-MG-BOOKNAV` của người đã nghỉ | Tổng theo đơn vị |
| --- | ---: | ---: | --- |
| **A: giữ người đã nghỉ, có cờ** | `13` (đo được, `care_basis = REAFLNK+DEC-CAP-MG-GAP`) | `22.214.317.000` (13 TK) | Số vẫn thuộc nhóm `G5` của người cũ, tổng không đổi |
| B: gán về trưởng nhóm | `0` | `0`, chuyển sang trưởng nhóm | Tổng nhóm không đổi, nhưng chỉ số báo không còn tiểu khoản cần chuyển |
| C: để trống | `13` | `0` | `22.214.317.000` không gắn nhóm nào, tổng nhóm và chi nhánh hụt đúng số đó |

Số của B, C suy từ cùng phép thử, không dựng model riêng. Dòng A đo trực tiếp; `test_th_nghiviec_flag_follows_work_status` xanh ở tình huống này, và đỏ khi bỏ cờ.

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

### Số liệu theo từng phương án (ngày `06/05`)

Số thật ở `mart`: `G5` 4 môi giới, 21 tiểu khoản, `30.673.713.000`; `G6` 4 môi giới, 45 tiểu khoản, `76.086.010.000`.

| Phương án | Cha của `G5`, `G6` | `CN3`: số TK, `CAP-MG-BOOKNAV` | `HO`: số TK, `CAP-MG-BOOKNAV` |
| --- | --- | ---: | ---: |
| **A (ĐƯỢC CHỌN)** | `CN3`, `CN3` | `66`, `106.759.723.000` | `200`, `316.320.659.000` |
| B: bỏ nút tạo vòng | Không có | `0`, `0` | `134`, `209.560.936.000` |
| C: dừng build | Không có số | Không có Gold ngày `06/05` | Không có Gold ngày `06/05`, các ngày sau chờ xử lý |

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
   - Với bảng sự kiện `finova_app_events` (`DQ-TRUNG-NGUYEN`): bản ghi trùng `event_id` (lấy `row_number() > 1` theo thứ tự xuất hiện) được tách sang `stg_finova_app__events__rejected` với `reason_code = 'DUPLICATE_EVENT'` để vừa khử trùng ở view chính (`634` dòng hợp lệ), vừa bảo toàn tổng đối soát `rows_landing (653) = rows_valid (634) + rows_rejected (19)` cho `GT-STG-RECON`.
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

Chọn **Phương án A**. `DQ-QUYEN` vẫn được đếm và báo ở `dq_mg_daily` (`EVENT_NOT_ASSIGNED`, `CANHBAO`). Test: `tests/gold/test_care_metrics.py`. Trên dữ liệu đề, điều kiện "vào ngày đang được giao" không đổi tử của môi giới nào, vì 7 tương tác `DQ-QUYEN` đều nhắm tiểu khoản môi giới không chăm sóc tại ngày hỏi; phép thử âm phải chèn sự kiện giả (`docs/matran_test.md`). "Ngày môi giới đang được giao tiểu khoản" trong tử của `CAP-MG-COVER30` xét theo bản phân công hệ thống biết tại cutoff(D) (`asof.sat_reaflnk__flex`), giữ đúng `INV-SEM-ASOF`.
