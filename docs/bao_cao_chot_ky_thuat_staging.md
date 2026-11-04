# BÁO CÁO TỔNG HỢP VÀ CHỐT QUYẾT ĐỊNH KỸ THUẬT TẦNG STAGING (CAP-MG)

> **Đã được thay thế (02/11/2026)** bởi [`ky_thuat_landing_staging.md`](ky_thuat_landing_staging.md). Nhiều mục dưới đây không còn đúng với code: khóa môi giới (KT-02), cửa sổ nạp ở staging và khử trùng giữ bản mới nhất (KT-03), ngưỡng 5 phút ghi cứng (KT-04), dò vòng 2 nút (KT-11), GT-STG-RECON theo bảng (KT-06). Giữ file này làm lịch sử.

- **Dự án:** Finova Capstone - Đề tài `CAP-MG` (Môi giới, Đơn vị và Chăm sóc)
- **Chuẩn đặc tả:** `FNV-CAP-DBT v1.5`
- **Mã định danh:** `REP-CAP-MG-STAGING-01`
- **Ngày lập:** 30/10/2026
- **Trạng thái:** **ĐÃ CHỐT VÀ HOÀN TẤT CÀI ĐẶT CODE**

---

## 1. Bối cảnh & Mục đích

Báo cáo này ghi nhận toàn diện các quyết định kỹ thuật, quy tắc xử lý dữ liệu và thiết kế kiến trúc đã thống nhất giữa Kỹ sư dữ liệu và Trưởng nhóm/Khách hàng cho tầng Staging (`models/staging/`). 

Tầng Staging đóng vai trò là cửa ngõ kiểm soát chất lượng dữ liệu, phân loại ranh giới giữa dòng hợp lệ (`stg_*`) và dòng bị từ chối (`stg_*__rejected`), chuẩn hóa khóa băm Data Vault 2.0 (`_hk`, `hashdiff`), và bảo toàn bất biến đối soát toàn vẹn `GT-STG-RECON`.

---

## 2. Bảng tổng hợp các quyết định kỹ thuật cốt lõi

| Mã quyết định | Vấn đề kỹ thuật | Phương án được chọn | Tác động cụ thể lên mã nguồn SQL |
| :--- | :--- | :--- | :--- |
| **DEC-MG-B1** | Tái sử dụng mã môi giới (`BRK017` cho 2 người khác nhau) | **Mã nguồn làm khóa hub, tách người bằng satellite** (`DEC-CAP-MG-BROKERKEY` PA A, đổi từ khóa ghép ngày 02/11/2026)<br>**PA 1:** Giữ người đã nghỉ việc, gắn cờ `is_active` | - Mọi staging mang mã (`stg_flex__broker`, `stg_flex__reaflnk`, `stg_finova_app__events`, `stg_manual__kpi`) tính cùng `broker_hk = dv_hash(['FLEX', broker_id])`, kèm `bkcc_broker`, `bk_broker`; test `test_stg_broker_hk_consistent` chặn lệch.<br>- `join_date` vào hashdiff; `broker_key = BROKERID:JOINDATE` là thuộc tính để Business Vault/Gold tách người.<br>- Giữ người đã nghỉ việc (`STATUS = 'C'`) và tính toán cờ `is_active = (status = 'A')`. |
| **DEC-MG-B2** | Khóa hợp đồng phân công `flex_reaflnk` | **`autoid` là một Hub riêng biệt** (`hub_reaflnk` / `hub_assignment`) | - `stg_flex__reaflnk`: `reaflnk_hk = dv_hash(['autoid'])` làm khóa Hub độc lập.<br>- Tạo thêm `reaflnk_link_hk = dv_hash(['autoid', 'reacctno', 'afacctno'])`.<br>- Chuẩn bị dữ liệu cho quy tắc **`fr_date` muộn hơn thắng** (`DEC-CAP-MG-OVERLAP`). |
| **DEC-MG-B3** | Cạnh chu trình cây tổ chức `flex_regrp` | **Giữ phiên bản cây hợp lệ liền trước** (`DEC-CAP-MG-CYCLE`) | - `stg_flex__regrp`: Bắt triệt để cạnh chu trình 2 chiều ($A \to B$ và $B \to A$) cùng tự lặp ($A \to A$).<br>- Đẩy các dòng vi phạm sang `__rejected` với `CYCLE_DETECTED`, giữ cây hợp lệ đi vào Raw/Business Vault. |
| **DEC-MG-D3** | Hai lô nạp cùng nằm trong một cửa sổ chạy `(lo_ts, hi_ts]` | **Sử dụng theo Hướng A** | - Staging giữ nguyên vẹn dữ liệu cả 2 lô để bảo toàn 100% lịch sử nạp.<br>- Tầng Raw Vault thực hiện khử trùng và kiểm soát thứ tự nạp bằng `lag(hashdiff) over (partition by hk order by ingested_ts)`. |
| **DEC-MG-D4** | Lô sửa / Dòng vắng mặt trong snapshot | **Lọc mới nhất theo `business_date` + Quản lý lịch sử theo cơ chế Insert-Only có `is_deleted`** | - Ở Satellite tầng Raw Vault, quản lý lịch sử theo `(business_date, load_ts)`.<br>- Dòng bị biến mất khỏi snapshot mới được đánh dấu cờ xóa mềm (`is_deleted = true`), không xóa vật lý. |
| **DEC-MG-D5** | Trùng lặp `event_id` giữa các lô trong cửa sổ | **Giữ bản `ingested_ts` mới nhất, mã từ chối `DUPLICATE_EVENT`** | - `stg_finova_app__events`: Phân hạng `row_number() over (partition by lower(event_id) order by ingested_ts desc, source_row_no desc)`.<br>- Bản hạng 1 đi vào view chính (đáp ứng test `unique`).<br>- Các bản sao chép còn lại chuyển sang `__rejected` với `reject_reason = 'DUPLICATE_EVENT'`. |

---

## 3. Chuẩn hóa khóa băm sai khác (`hashdiff`) & Kiểu dữ liệu

Để đảm bảo tính xác định và phát hiện chính xác mọi thay đổi dữ liệu từ nguồn mà không bị bỏ sót, các khóa băm `hashdiff` được tái cấu trúc triệt để:

1. **`stg_flex__regrp`:**
   - Bổ sung `nullif(upper(trim(parentid)), '')` vào `hashdiff`. Tránh mất dấu vết khi đơn vị thay đổi cấp cha trực thuộc.
2. **`stg_flex__reaflnk`:**
   - Bổ sung `upper(trim(reacctno))` và `upper(trim(afacctno))` vào `hashdiff`. Đảm bảo nếu phân công đổi người môi giới hoặc đổi tiểu khoản thì phát hiện được ngay.
3. **`stg_flex__nav`:**
   - Bổ sung cột `hashdiff = dv_hash(['trim(nav)::numeric(20, 4)::text'])`. Đảm bảo khi một ngày giao dịch có bản điều chỉnh số liệu NAV thì Satellite ghi nhận phiên bản mới.
4. **`stg_manual__kpi`:**
   - Chuẩn hóa số thập phân `replace(',', '.')::numeric(20,4)::text` trước khi băm `hashdiff`. Tránh việc `3.5` và `3.50` sinh 2 mã hash khác nhau. Bổ sung `trim(fullname)` vào hash.
5. **`stg_flex__broker`:**
   - Băm nhất quán toàn bộ các thuộc tính mô tả: `fullname`, `email`, `mobile`, `grpid`, `leave_date`, `status`.

---

## 4. Chuẩn hóa bộ lọc & Biểu thức chính quy (Regex)

1. **Hỗ trợ định dạng ngày kép (`DD/MM/YYYY` và `YYYY-MM-DD`):**
   - Áp dụng biểu thức `CASE WHEN` nhận diện regex linh hoạt trên toàn bộ các cột: `joindate`, `leavedate`, `effdate`, `frdate`, `todate`, `lastchange`, `txdate`, `approved_date`.
   - Ngăn chặn triệt để lỗi sập truy vấn khi nguồn dữ liệu có sự thay đổi định dạng ngày giữa các lô.
2. **Siết chặt regex lỗi công thức bảng tính Excel (`DQ-CONGTHUC`):**
   - Thay thế biểu thức quá rộng `^#.*` bằng danh mục chuẩn các lỗi công thức Excel theo đặc tả:
     ```regex
     ^#(REF!|DIV/0!|VALUE!|NAME\?|N/A|NUM!|NULL!)
     ```
   - Tránh việc phân loại nhầm các chuỗi văn bản nghiệp vụ hợp lệ vô tình bắt đầu bằng ký tự `#`.
3. **Cấu hình độ lệch giờ thiết bị (`DQ-TUONGLAI`):**
   - Ngưỡng lệch giờ tối đa giữa thiết bị và server được chuẩn hóa: `interval '5 minutes'`.
   - Khi `raw_event_ts > server_ts + interval '5 minutes'`, gán `event_ts = server_ts` và bật cờ `is_future_ts_fixed = true`.

---

## 5. Bất biến đối soát bảo toàn dòng (`GT-STG-RECON`)

- **Bất biến toán học:**
  $$\sum \text{Dòng Landing trong cửa sổ} = \sum \text{Dòng Staging Hợp lệ} + \sum \text{Dòng Staging Bị từ chối}$$
- **Cơ chế thực thi:**
  - Singular test [`test_stg_reconciliation.sql`](file:///c:/Users/phuc.nguyenduc/Documents/exam/cap-mg-phucnd/finova-dbt/tests/staging/test_stg_reconciliation.sql) thực hiện đối soát tự động trên cả 6 nguồn dữ liệu trong mọi lần chạy.
  - Phân loại lỗi theo mô hình **Thác nước đơn định (Single-defect Precedence Waterfall)**: mỗi dòng lỗi chỉ nhận đúng 1 mã `reject_reason` ưu tiên cao nhất, tuyệt đối không nhân đôi dòng.

---

## 6. Kết quả kiểm tra Khung chuẩn (`check_khung.py`)

- Lệnh chạy: `python tools/check_khung.py --repo . --de MG`
- **Kết quả: 14/14 ĐẠT (100%)**
  - Không vi phạm hardcode bí mật / DSN.
  - Không vi phạm hàm thời gian hiện tại (`QT-NO-NOW`).
  - Đủ cấu trúc 15 thư mục/tệp bắt buộc và 7 selector.
  - Đủ 3 macro nền tảng: `generate_schema_name`, `dv_hash`, `dv_window`.
  - Pass bài test Known-Answer Test (KAT) cho 4 trường hợp băm hex.

---

## 7. Các bước triển khai tiếp theo

1. **Bước A1 (Thực thi ngay):**
   Chạy lệnh `dbt build --selector cap_mg_staging` trên môi trường terminal local để kiểm tra số liệu thực tế của toàn bộ 12 view và test đối soát.
2. **Bước A2 (Commit Git):**
   Thực hiện commit toàn bộ tầng Staging và các tệp tài liệu đi kèm vào nhánh `main`.
3. **Bước A3 (Chuyển tiếp Milestone Day 6-7):**
   Tiến hành dựng tầng **Raw Vault** (`models/atomic/raw/`), bao gồm các Hubs (`hub_broker`, `hub_regrp`, `hub_account`, `hub_reaflnk`), Links, và Satellites theo các khóa đã chốt ở báo cáo này.

