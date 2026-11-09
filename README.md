# CAP-MG: Môi giới, đơn vị và chăm sóc

Capstone dbt Finova (`FNV-CAP-DBT v1.5`), đề `CAP-MG`. Luồng: gói đề `inbound/` → loader → `landing` + `ctrl` → dbt `staging` → raw vault → business vault → as-of → gold.

## Cấu trúc

| Thư mục | Nội dung |
|---|---|
| `setup/` | `bootstrap.sql` (role, schema; role đọc Gold `finova_app`), `ctrl.sql` (sổ nạp, sổ chạy; mẫu của gói đề), `ctrl_runner.sql` (lô bị T-GUARD chặn, số dòng bị loại), `ctrl_log.sql` (bảng lỗi tập trung `ctrl.error_log`) |
| `contracts/` | Hợp đồng nguồn `*.yml`: khóa, cột, mẫu, quy tắc loại (D-HOPDONG) |
| `customers/ctcka/thresholds.yaml` | Ngưỡng nghiệp vụ, nguồn duy nhất (INV-M6) |
| `loader/load.py` | Nạp lô theo `manifest.csv` vào `landing`, ghi `ctrl.batch_log` (D-LOADER) |
| `runner/run.py` | Chạy pipeline theo ngày giao dịch: loader tới cutoff(D), cửa sổ `(lo_ts, hi_ts]`, T-GUARD, dbt, ghi `ctrl.batch_run`, `ctrl.reject_count` |
| `runner/guard.py` | Xem và xử lý lô bị T-GUARD chặn (`list`, `accept`) |
| `runner/probes.py` | Chạy các file SQL ở `evidence/probes/`, ghi đáp án câu hỏi kiểm vào `evidence/probes.csv` |
| `finova-dbt/` | Project dbt `cap_mg`; selector ở `selectors.yml` |
| `tests/` | pytest cho loader, staging, raw vault, as-of, Business Vault và RLS của Gold |
| `evidence/` | D-BANGCHUNG: `probes/*.sql` (mỗi câu hỏi kiểm một file SQL thuần), `probes.csv`; `run_daily/`, `run_rerun/`, `run_full_refresh/` (run_results.json của từng lần gọi dbt, `row_counts.csv`), `row_counts_compare.csv` |
| `runner/init_db.py`, `runner/evidence.py` | Dựng database từ các file setup; thu bằng chứng ba lần chạy trên database riêng `<CAP_DBNAME>_evidence` |
| `docs/` | Khảo sát, quyết định, sổ kỹ thuật, ma trận test |

## Chuẩn bị (một lần)

1. **Python.** Dự án yêu cầu Python 3.12. Trên máy bật Smart App Control, bản Python uv tự tải không có chữ ký số và bị chặn; cài bản python.org (`winget install -e --id Python.Python.3.12 --scope user`). `pyproject.toml` đặt `python-preference = "only-system"` nên uv dùng bản này.
   ```powershell
   uv sync
   ```
   Máy bật Application Control có thể chặn cả `.venv/Scripts/dbt.exe` (`os error 4551`). Khi đó gọi dbt qua Python, cùng bản đã ghim: `uv run python -c "from dbt.cli.main import cli; cli()" <lệnh dbt>` thay cho `uv run dbt <lệnh dbt>`; `check_khung.py` nhận lệnh này qua `--dbt-cmd`. Runner gọi dbt trong tiến trình Python nên không bị ảnh hưởng.

   Windows chưa bật long paths thì đặt repo ở đường dẫn ngắn, dưới khoảng 115 ký tự. Gói `metricflow_semantic_interfaces` có file sâu hơn 140 ký tự trong `.venv`; đường dẫn đầy đủ vượt 260 ký tự thì `uv sync` vẫn xong nhưng dbt báo `ModuleNotFoundError` khi chạy.
2. **Biến môi trường.** Chép `.env.example` thành `.env` (đã nằm trong `.gitignore`) và điền `FINOVA_PG_PASSWORD`, `CAP_DBNAME`. Mặc định của repo là cổng `5436` (container `finova-pg16-dev`, REQ-ENV-07); máy chạy PostgreSQL ở cổng khác thì đặt `CAP_PGPORT` trong `.env`, không sửa mặc định trong repo. Loader không tự đọc `.env`, nên mọi lệnh chạy qua `uv run --env-file .env`. Gói đề không nằm cạnh repo thì đặt `CAP_MG_KIT_DIR` (thư mục `CAP-MG`); loader, runner và pytest cùng đọc biến này.
3. **dbt profile.** Chép `finova-dbt/profiles.example.yml` thành `finova-dbt/profiles.yml` (đã nằm trong `.gitignore`).
4. **Database.** `python -m runner.init_db` tạo database `CAP_DBNAME` nếu chưa có, rồi chạy `setup/bootstrap.sql`, `setup/ctrl.sql`, `setup/ctrl_runner.sql`, `setup/ctrl_log.sql` bằng user `postgres`. Cả bốn file chạy lại nhiều lần không lỗi, nên lệnh này cũng vậy (chạy bằng `psql` từng file cũng được).

## Dựng lại trong 5 lệnh (D-RUNBOOK)

Sau phần chuẩn bị mục 1–3 (Python, `.env`, `profiles.yml`), từ database chưa có:

```powershell
uv sync                                                    # 1. môi trường ghim phiên bản
uv run --env-file .env python -m runner.init_db            # 2. database, schema, role, năm bảng ctrl
uv run --env-file .env python -m runner.run                # 3. từng ngày giao dịch 17/04 -> 15/05: loader tới cutoff(D), staging, raw vault, as-of, Business Vault, Gold
uv run --env-file .env python -m runner.probes             # 4. đáp án câu hỏi kiểm -> evidence/probes.csv
$env:RUN_PT_FULL = "1"; uv run --env-file .env pytest -q tests   # 5. kiểm: loader, staging, raw vault (PT-FULL, PT-IDEMP, T-GUARD), as-of, RLS
```

Thu bằng chứng (D-BANGCHUNG, khoảng 10 phút, database riêng `<CAP_DBNAME>_evidence` dựng lại từ đầu): `uv run --env-file .env python -m runner.evidence` chạy lịch tới 14/05, rồi lần chạy theo ngày 15/05, chạy lại 15/05, full refresh, ghi vào `evidence/run_*/` và so số dòng, md5 ở `evidence/row_counts_compare.csv` (PT-IDEMP, PT-FULL). Runner nhận thêm `--evidence-dir DIR` để ghi bằng chứng cho một lần chạy bất kỳ.

Kiểm D-DBT riêng (schema dbt trống, landing đã nạp): `dbt build --selector cap_mg_all --vars '{lo_ts: "-infinity", hi_ts: "2026-05-15T23:59:59+07:00", as_of_date: "2026-05-15"}'` dựng mọi tầng cho một ngày; `cap_mg_all` không gồm unit test (cần bảng incremental đã có), chạy sau bằng bước 5 ở mục dưới.

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

# 4. Raw vault theo lịch: runner chạy từng ngày giao dịch 17/04 -> 15/05 (gồm cả bước 1, 2)
uv run --env-file .env python -m runner.run
uv run --env-file .env python -m runner.run --full-refresh --skip-load   # PT-FULL: một cửa sổ (-infinity, hi]

# 5. Unit test mẫu nạp (PT-ABA, PT-ESAT-SWITCH, PT-REVDATE, sts); cần raw vault đã dựng một lần
uv run --env-file .env dbt test --select "test_type:unit" @dbt --vars '{lo_ts: "-infinity", hi_ts: "2026-05-15T23:59:59+07:00"}'

# 6. PT-FULL, PT-IDEMP, GT-BV-REBUILD, TC-CAP-MG-BACKDATE, T-GUARD, reject_count trên database thử <CAP_DBNAME>_ptfull dựng mới
$env:RUN_PT_FULL = "1"; uv run --env-file .env pytest -q tests

# 7. Test as-of (PT-ASOF-SINGLE, PT-NOFUTURE, TC-SLV-NOCUTOFF, TC-CAP-MG-FUTUREEFF) trên CAP_DBNAME; chỉ đọc
uv run --env-file .env pytest -q tests/asof

# 8. Test Gold: TC-CAP-MG-RLS đọc bằng role finova_app với từng người xem trong org_roles; DQ-QUYEN, TH-NHAPTAY, TH-NGHIVIEC, DEC-CAP-MG-BROKERKEY; chỉ đọc
uv run --env-file .env pytest -q tests/gold

# 9. Đáp án câu hỏi kiểm -> evidence/probes.csv (cần runner đã dựng Gold tới 15/05)
uv run --env-file .env python -m runner.probes
```

Runner chạy mỗi ngày: staging → raw vault → (view as-of, chỉ khi thiếu view hoặc full refresh) → Business Vault → Gold của ngày D. Full refresh dựng lại raw vault một cửa sổ, rồi Business Vault và Gold cho mọi ngày giao dịch tới ngày cuối.

**Đọc Gold như ứng dụng (RLS).** Role `finova_app` chỉ thấy dòng thuộc phạm vi của người xem trong `org_roles`; chưa đặt người xem thì không thấy dòng nào:
```sql
set role finova_app;
select set_config('finova.viewer_id', 'LEAD-G2', false);
select account_id, broker_key, care_basis from mart.dim_account_care_daily where as_of_date = '2026-05-15';
```

**Tra as-of bằng tay.** View trong schema `asof` đọc mốc từ GUC của phiên; chưa đặt thì báo lỗi:
```sql
set role finova_dbt;
select set_config('finova.asof_date', '2026-04-28', false),
       set_config('finova.asof_cutoff', '2026-04-29T00:00:00+07:00', false);   -- cutoff(D) = 00:00 ngày D+1
select broker_id, fr_date, to_date from asof.esat_reaflnk__flex where afacctno = '9994000016';
```
Đặt `finova.asof_cutoff` muộn hơn cutoff(D) là hỏi "giờ biết gì về ngày D", không dùng cho số liệu theo ngày (TH-LUIHIEULUC).

Runner chạy cho database trống hoặc tiếp tục từ lần SUCCESS cuối trong `ctrl.batch_run`.

Kết quả mong đợi trên gói đề (kiểm lại 10/11/2026, database mới): loader 63 lô `LOADED` (5.959 dòng) và 41 lô `SKIPPED_DUP`; `dbt build` staging PASS 75, WARN 1 (DQ-MOCOI, G7 → CN9), ERROR 0; raw vault 19 bảng, WARN 1 (GT-HUB-NOMASTER, CN9); runner 19 lần chạy SUCCESS; `dbt test --select test_type:unit` PASS 13 (11 unit test: 9 raw vault, 2 Gold; 2 hook); 8 view as-of; Business Vault 4 bảng × 19 ngày, mỗi lần `cap_mg_bv` PASS 13; Gold 5 bảng × 19 ngày, mỗi lần `cap_mg_gold` PASS 21; `RUN_PT_FULL=1 pytest -q tests` 61 passed; `cap_mg_all` từ schema trống PASS 292, WARN 2; `runner.evidence` lệch 0 giữa ba lần chạy; `runner.probes` 11 dòng đáp án ở `evidence/probes.csv`.

## Tra lỗi

Mọi lỗi và cảnh báo của loader, runner và dbt ghi vào một bảng `ctrl.error_log` (thay cho thư mục `logs/`). Mỗi dòng cho biết lỗi ở tầng nào (`component`), bước nào (`step`: `check_file`, `process_batch`, `t_guard`, `run_day`, tên selector dbt) và đối tượng nào (`object_name`: file nguồn, bảng, `unique_id` của model hoặc test).

```sql
select error_id, severity, component, step, object_name, run_id, batch_id, error_code, message
from ctrl.error_log
order by error_id desc
limit 50;
```

| `error_code` | Ghi khi |
|---|---|
| `SHA256_MISMATCH`, `ROWCOUNT_MISMATCH`, `FILE_MISSING` | Loader từ chối cả lô |
| `LOAD_REJECT` (WARN) | Lô có dòng không tính được `event_ts`, chi tiết ở `ctrl.load_reject` |
| `BLOCKED_BY_GUARD` | T-GUARD chặn lô nạp muộn mang giờ cũ (mỗi lô một dòng) |
| `MODEL_ERROR`, `TEST_FAIL`, `TEST_ERROR`, `TEST_WARN` (WARN), `SEED_ERROR` | Từng node dbt không xanh |
| `DBT_EXCEPTION`, `EXCEPTION` | dbt hoặc Python dừng đột ngột; `message` chứa traceback |

Sổ nạp của đề (`batch_log`, `load_reject`) giữ nguyên; dòng bị loại ở staging vẫn ở các view `__rejected`.

## Nạp lại và nạp bù

- **Chạy lại loader** (vô tình hay theo lịch) an toàn: dòng manifest đã có trong sổ (theo `arrival_seq`) bị bỏ qua, không thêm dòng landing.
- **Nguồn gửi lại** cùng `batch_id` thì ghi `SKIPPED_DUP/ALREADY_LOADED`; cùng nội dung với lô LOADED gần nhất của bảng thì `SKIPPED_DUP/DUP_CONTENT` (bản chụp quay về nội dung một lô cũ hơn vẫn được nạp, KT-22); nội dung khác với `batch_id` mới thì nạp như lô mới, raw vault ghi phiên bản mới nếu hashdiff đổi.
- **Nạp bù theo ngày:** chạy với `--as-of-date`, lần sau chạy tiếp; lô sau mốc chưa vào sổ nên được nhặt.
- **Lô bị từ chối** (`REJECTED_BATCH`) đã vào sổ nên không tự thử lại; cần dòng manifest mới (nguồn gửi lại).
- **Staging** là view, chạy lại bao nhiêu lần cũng cùng kết quả.

## Xử lý T-GUARD

- **Dấu hiệu.** Runner thoát mã 1 với `-> BLOCKED_BY_GUARD`; `ctrl.batch_run.status = 'BLOCKED_BY_GUARD'`. Lô bị chặn là lô LOADED nạp sau lần SUCCESS gần nhất (`log_id > max_log_id`) mà mang `ingested_ts ≤ lo_ts`, ví dụ file cũ gửi lại muộn. Lô đó nằm trước mọi cửa sổ còn chạy, nên nếu chạy tiếp, vault sẽ không bao giờ nhận lô.
- **Lệnh kiểm.**
  ```powershell
  uv run --env-file .env python -m runner.guard list    # lô chưa xử lý và lệnh gợi ý
  ```
  hoặc `select * from ctrl.v_guard_open;`. Lịch sử các lần chặn ở `ctrl.guard_block`, quyết định ở `ctrl.guard_resolution`.
- **Cách xử lý đã chọn: full refresh** (DEC theo RV-10 ở `docs/ky_thuat_raw_vault.md`):
  ```powershell
  uv run --env-file .env python -m runner.run --full-refresh --skip-load --to <ngày D bị chặn>
  uv run --env-file .env python -m runner.run --from <D+1> --to <ngày cần tới>   # chạy tiếp theo lịch
  ```
  Full refresh SUCCESS tự ghi `FULL_REFRESH` cho các lô bị chặn mà nó phủ; lần chạy sau T-GUARD xanh.
- **Cách khác: cho chạy tiếp, chưa đưa lô vào vault** (khi lô không mang thay đổi, hoặc phải ra số đúng hạn rồi full refresh sau):
  ```powershell
  uv run --env-file .env python -m runner.guard accept --log-id <log_id> --note "<lý do>"
  ```
  Lô vào vault ở lần full refresh kế tiếp, với `ingested_ts` cũ của nó.
- **Thời gian chạy đo được** (máy DEV, dữ liệu đề, 03/11/2026): full refresh raw vault một cửa sổ `(-infinity, 15/05]` mất 16–17 giây (2 lần đo); một lần chạy theo ngày mất 12–16 giây, trung bình 13 giây (21 lần đo). Cả hai chủ yếu là thời gian khởi động dbt; dữ liệu đề nhỏ nên full refresh gần như không đắt hơn một ngày.

## Tài liệu

- `docs/khaosat.md`: khảo sát dữ liệu (D-KHAOSAT)
- `docs/decisions.md`: quyết định nghiệp vụ `DEC-CAP-MG-*` (D-QUYETDINH)
- `docs/ky_thuat_landing_staging.md`: sổ kỹ thuật landing và staging (`KT-01` đến `KT-23`)
- `docs/nhatky_staging.md`: nhật ký nạp landing và dựng staging
- `docs/ky_thuat_raw_vault.md`: sổ kỹ thuật raw vault và runner (`RV-01` đến `RV-12`)
- `docs/ky_thuat_asof_bv.md`: sổ kỹ thuật tầng as-of và Business Vault (`AB-01` đến `AB-08`)
- `docs/ky_thuat_gold.md`: sổ kỹ thuật tầng Gold, RLS, bảng chất lượng (`GD-01` đến `GD-08`)
- `docs/chatluong.md`: báo cáo chất lượng theo ngày, giải thích từng mã lỗi (D-DQ, cùng `mart.dq_mg_daily`)
- `docs/matran_test.md`: ma trận phủ DQ, TH, test và phép thử âm (D-TEST)
- `docs/pr_description.md`: mô tả PR theo Phụ lục D (D-PR)
- `docs/Báo cáo.pdf`: ghi chú tổng quan theo tầng, chuẩn bị cho viva
