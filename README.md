# CAP-MG: Môi giới, đơn vị và chăm sóc

Capstone dbt Finova (`FNV-CAP-DBT v1.5`), đề `CAP-MG`. Luồng: gói đề `inbound/` → loader → `landing` + `ctrl` → dbt `staging` → raw vault → business vault → as-of → gold.

## Cấu trúc

| Thư mục | Nội dung |
|---|---|
| `setup/` | `bootstrap.sql` (role, schema), `ctrl.sql` (sổ nạp, sổ chạy) |
| `contracts/` | Hợp đồng nguồn `*.yml`: khóa, cột, mẫu, quy tắc loại (D-HOPDONG) |
| `customers/ctcka/thresholds.yaml` | Ngưỡng nghiệp vụ, nguồn duy nhất (INV-M6) |
| `loader/load.py` | Nạp lô theo `manifest.csv` vào `landing`, ghi `ctrl.batch_log` (D-LOADER) |
| `finova-dbt/` | Project dbt `cap_mg`; selector ở `selectors.yml` |
| `tests/` | pytest cho loader và staging |
| `docs/` | Khảo sát, quyết định, sổ kỹ thuật, ma trận test |

## Chuẩn bị (một lần)

1. **Python.** Dự án yêu cầu Python 3.12. Trên máy bật Smart App Control, bản Python uv tự tải không có chữ ký số và bị chặn; cài bản python.org (`winget install -e --id Python.Python.3.12 --scope user`). `pyproject.toml` đặt `python-preference = "only-system"` nên uv dùng bản này.
   ```powershell
   uv sync
   ```
2. **Biến môi trường.** Chép `.env.example` thành `.env` (đã nằm trong `.gitignore`) và điền `FINOVA_PG_PASSWORD`, `CAP_DBNAME`. Mặc định của repo là cổng `5436` (container `finova-pg16-dev`, REQ-ENV-07); máy chạy PostgreSQL ở cổng khác thì đặt `CAP_PGPORT` trong `.env`, không sửa mặc định trong repo. Loader không tự đọc `.env`, nên mọi lệnh chạy qua `uv run --env-file .env`.
3. **dbt profile.** Chép `finova-dbt/profiles.example.yml` thành `finova-dbt/profiles.yml` (đã nằm trong `.gitignore`).
4. **Database.** Tạo database `CAP_DBNAME`, chạy `setup/bootstrap.sql` rồi `setup/ctrl.sql` bằng user `postgres`.

## Chạy

```powershell
$dbt = @("--project-dir", "finova-dbt", "--profiles-dir", "finova-dbt")

# 1. Nạp landing: toàn bộ manifest, hoặc đến một ngày nghiệp vụ D (cutoff 00:00 ngày D+1 giờ VN)
uv run --env-file .env python -m loader.load
uv run --env-file .env python -m loader.load --as-of-date 2026-04-20

# 2. Staging: seed, 12 view, test
uv run --env-file .env dbt debug @dbt
uv run --env-file .env dbt build --selector cap_mg_staging @dbt

# 3. pytest (loader và TC-NEN-HASH-TZ của staging; cần staging đã build)
uv run --env-file .env pytest -q
```

Kết quả mong đợi trên gói đề (02/11/2026): loader 61 lô `LOADED` (5.939 dòng) và 43 lô `SKIPPED_DUP`; `dbt build` PASS 69, WARN 1 (DQ-MOCOI, G7 → CN9), ERROR 0; pytest 15 passed.

## Nạp lại và nạp bù

- **Chạy lại loader** (vô tình hay theo lịch) an toàn: dòng manifest đã có trong sổ (theo `arrival_seq`) bị bỏ qua, không thêm dòng landing.
- **Nguồn gửi lại** cùng `batch_id` thì ghi `SKIPPED_DUP/ALREADY_LOADED`; cùng nội dung file thì `SKIPPED_DUP/DUP_CONTENT`; nội dung khác với `batch_id` mới thì nạp như lô mới, raw vault ghi phiên bản mới nếu hashdiff đổi.
- **Nạp bù theo ngày:** chạy với `--as-of-date`/`--cutoff`, lần sau chạy tiếp; lô sau mốc chưa vào sổ nên được nhặt.
- **Lô bị từ chối** (`REJECTED_BATCH`) đã vào sổ nên không tự thử lại; cần dòng manifest mới (nguồn gửi lại).
- **Staging** là view, chạy lại bao nhiêu lần cũng cùng kết quả.

## Tài liệu

- `docs/khaosat.md`: khảo sát dữ liệu (D-KHAOSAT)
- `docs/decisions.md`: quyết định nghiệp vụ `DEC-CAP-MG-*` (D-QUYETDINH)
- `docs/ky_thuat_landing_staging.md`: sổ kỹ thuật landing và staging (`KT-01` đến `KT-21`)
- `docs/matran_test.md`: ma trận test và phép thử âm (D-TEST)
