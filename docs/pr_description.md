# CAP-MG: môi giới, đơn vị và chăm sóc (feat/cap-mg-phucnd → main)

Mô tả PR theo Phụ lục D (FNV-PROMPT-BOOT-001 §6).

## 1. Mã đề và danh sách bàn giao

Mã đề: `CAP-MG`. Học viên: phucnd. Đề bài `FNV-CAP-DBT v1.5`.

| Mã | Vị trí |
|---|---|
| D-KHUNG | `pyproject.toml`, `uv.lock`, `setup/`, `finova-dbt/`, `evidence/khung.json` |
| D-KHAOSAT | `docs/khaosat.md` |
| D-HOPDONG | `contracts/*.yml` (6 bảng) |
| D-LOADER | `loader/`, `tests/loader/` |
| D-DBT | `finova-dbt/` |
| D-TEST | `docs/matran_test.md` |
| D-DQ | `mart.dq_mg_daily`, `docs/chatluong.md` |
| D-BANGCHUNG | `evidence/` |
| D-QUYETDINH | `docs/decisions.md` |
| D-RUNBOOK | `README.md` |
| D-PR | File này; nhánh `feat/cap-mg-phucnd` merge thẳng vào `main`, không qua PR trên GitHub |

D-VIVA trình bày trực tiếp. `docs/Báo cáo.pdf` là ghi chú tổng quan theo tầng, chuẩn bị cho viva.

## 2. Tiêu chí nghiệm thu và bằng chứng

| Tiêu chí | Lệnh | Kết quả |
|---|---|---|
| Chạy từ schema trống theo D-RUNBOOK | Bản clone sạch, database mới: `runner.init_db`, `runner.run`, `runner.probes` | 19 lần chạy SUCCESS; `evidence/probes.csv` trùng từng dòng |
| D-DBT xanh từ schema trống | `dbt build --selector cap_mg_all`, D = 15/05 | PASS 291, WARN 2, ERROR 0 |
| Unit test | `dbt test --select test_type:unit` | 11 PASS |
| Loader, test các tầng | `RUN_PT_FULL=1 pytest -q tests` | 61 test: 50 passed trên bản clone sạch, 11 test mới passed trên database dựng mới |
| Khung project | `check_khung.py --repo . --de MG --dbt` | 22 ĐẠT, 0 KHÔNG ĐẠT (`evidence/khung.json`) |
| Không dùng hàm thời gian, không có bí mật | KHUNG-NONOW, KHUNG-BIMAT | ĐẠT |
| PT-FULL, PT-IDEMP | `runner.evidence` | 59 bảng và view, lệch 0 (mục 5) |
| Khớp D-DQ | `test_gold_dq_recon` | 104 lô, 5.959 dòng landing, 39 dòng bị loại |
| Phép thử âm | `docs/matran_test.md` | Có cho mọi test của Bảng 24, Bảng 70; chạy trên máy thật |

## 3. Quyết định đã chốt

Quyết định của đề, chi tiết và số liệu theo từng phương án ở `docs/decisions.md`:

| Mã | Chọn | Số liệu chính |
|---|---|---|
| DEC-CAP-MG-BROKERKEY | Mã nguồn làm khóa hub, tách người bằng satellite | Người mới mang `BRK017`: 0 tiểu khoản, 0 tương tác; bỏ lọc khoảng làm việc thì 16 tương tác |
| DEC-CAP-MG-OVERLAP | `FRDATE` muộn hơn thắng | 05/05: `BRK021` 15.114.758.000, `BRK010` 16.244.048.000; tính cho cả hai thì thừa 7.770.720.000 |
| DEC-CAP-MG-GAP | Giữ người đã nghỉ, có cờ | Dữ liệu đề 0 tiểu khoản; tình huống giữ 13 tiểu khoản tới 05/05 cho `KH-ORPHANCNT = 13` |
| DEC-CAP-MG-CYCLE | Loại dòng tạo vòng, giữ cây trước | 06/05: `CN3` 66 tiểu khoản; bỏ nút thì `HO` còn 134/200 |

Quyết định thêm: DEC-CAP-MG-STAGING-RULES (loại cả dòng có ô lỗi công thức, thứ tự ưu tiên lỗi), DEC-CAP-MG-ORPHAN, DEC-CAP-MG-RLSROLE, DEC-CAP-MG-INTER30.

Quyết định của Finova gặp phải:

- DEC-ELT-HUBSRC: hub nhận khóa theo nguồn chủ; khóa thiếu nguồn chủ báo ở GT-HUB-NOMASTER.
- DEC-ELT-REJECT: runner ghi số dòng bị loại vào `ctrl.reject_count`.
- DEC-ELT-WINDOW, DEC-ELT-STGVIEW, DEC-ELT-RESTATE: cửa sổ `(lo_ts, hi_ts]`, staging là view, NAV đính chính theo T-SAT-DAY. Xem `docs/ky_thuat_raw_vault.md`.
- DEC-SA-BROKERKEY: chưa chốt; đề xuất dùng `RECFLNK.AUTOID` nhưng gói đề không có `RECFLNK`, xem DEC-CAP-MG-BROKERKEY.

## 4. Chỗ làm khác đề bài hoặc spec

| Chỗ khác | Lý do |
|---|---|
| Thêm role `finova_app` ngoài hai role của Bảng 13 | RLS không áp cho chủ bảng; DEC-CAP-MG-RLSROLE |
| Thêm `setup/ctrl_runner.sql`, `setup/ctrl_log.sql`, `ctrl.error_log` | Sổ T-GUARD, số dòng bị loại, lỗi tập trung thay thư mục `logs/` |
| Model nằm phẳng trong `models/staging/`, `models/atomic/raw/`, không chia thư mục theo nguồn, miền | Đề chỉ có 6 bảng nguồn; `check_khung.py` đạt |
| `profiles.yml` đặt trong `finova-dbt/` và nằm trong `.gitignore`, không đặt ngoài repo | Mục E.3 cho phép khi có trong `.gitignore`; file chỉ đọc biến môi trường, không chứa mật khẩu |
| `evidence/run_*/` chia theo lần chạy, không đặt tên `run_results_*.json` | Mỗi lần chạy có nhiều lần gọi dbt, mỗi lần một file |
| `cap_mg_all` không gồm unit test | Unit test cần bảng incremental đã có; chạy riêng sau build |
| Runner gọi dbt trong tiến trình Python | Máy phát triển bị Application Control chặn `dbt.exe`; `check_khung.py` dùng `--dbt-cmd` |
| Máy phát triển dùng PostgreSQL 16 cổng 5432, không phải container cổng 5436 | Đặt `CAP_PGPORT` trong `.env`; mặc định trong repo vẫn là 5436 |

## 5. Kết quả PT-FULL và PT-IDEMP

`runner.evidence` trên database riêng; số dòng và md5 so ở `evidence/row_counts_compare.csv`, 59 bảng và view, lệch 0.

| Tầng | Lần chạy theo ngày | Lần chạy lại | Full refresh |
|---|---:|---:|---:|
| landing | 5.959 | 5.959 | 5.959 |
| staging | 6.027 | 6.027 | 6.027 |
| atomic | 14.090 | 14.090 | 14.090 |
| asof (cutoff 15/05) | 5.157 | 5.157 | 5.157 |
| mart | 7.342 | 7.342 | 7.342 |

## 6. Việc còn mở và rủi ro đã biết

- DEC-SA-BROKERKEY của Finova chưa chốt. Khi chốt, khóa hub môi giới có thể phải đổi.
- Trên dữ liệu đề, điều kiện "vào ngày đang được giao" của CAP-MG-COVER30 và cờ `is_carer_inactive` không đổi số nào. Hai quy tắc chỉ được chứng minh bằng dữ liệu giả trên database thử, xem `docs/matran_test.md`.
- CAP-MG không có lô về muộn hay lô phát lại (`available_ts = commit_ts` ở cả 104 dòng manifest). T-GUARD chỉ được kiểm bằng lô giả trong pytest.
- `dq_mg_daily` ghi `test_id` của DQ-QUYEN là `met_broker_daily`, chưa đổi sang tên test mới để giữ nguyên bằng chứng chạy; tên test ở `docs/chatluong.md`.
- Windows chưa bật long paths: repo phải nằm ở đường dẫn ngắn hơn khoảng 115 ký tự, xem `README.md`.
