# Nhật ký kỹ thuật: nạp landing và tầng staging (02/11/2026)

Ghi lại theo trình tự những gì đã làm, lệnh đã chạy, sự cố gặp phải và cách xử lý, để làm lại được. Lý do thiết kế chi tiết nằm ở `docs/ky_thuat_landing_staging.md` (KT-01 đến KT-21); danh sách test và phép thử âm ở `docs/matran_test.md`.

Mọi lệnh chạy trong thư mục `cap-mg-phucnd`, PowerShell.

---

## 1. Chuẩn bị môi trường

### 1.1 Biến môi trường

- Chép `.env.example` thành `.env`, điền `FINOVA_PG_PASSWORD`, `CAP_DBNAME=cap_mg_phucnd`, `CAP_PGHOST=127.0.0.1`, `CAP_PGPORT=5432`.
- **Loader không tự đọc `.env`** (không dùng `dotenv`). Mọi lệnh phải chạy qua `uv run --env-file .env ...`, nếu không sẽ gặp `KeyError: 'CAP_DBNAME'`.
- **Cổng:** repo mặc định `5436` (container `finova-pg16-dev`, REQ-ENV-07). Máy này chạy PostgreSQL 16 dạng service Windows `postgresql-x64-16` ở cổng `5432`, nên đặt `CAP_PGPORT=5432` trong `.env`, không sửa mặc định trong repo.

### 1.2 Sự cố: Smart App Control chặn Python

**Dấu hiệu.**
```
error: Failed to spawn: python
  cause: An Application Control policy has blocked this file. (os error 4551)
```
Hôm trước vẫn chạy bình thường, chưa tắt máy.

**Chẩn đoán.**
```powershell
Get-WinEvent -LogName 'Microsoft-Windows-CodeIntegrity/Operational' -MaxEvents 15 |
  Where-Object { $_.Id -in 3033,3077 } | Format-List TimeCreated, Id, Message
(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy').VerifiedAndReputablePolicyState   # 1 = SAC đang chặn
Get-AuthenticodeSignature .venv\Scripts\python.exe
```
- Sự kiện 3033/3077, Policy ID `{0283ac0f-fff1-49ae-ada1-8a933130cad6}` (Smart App Control), file bị chặn là `.venv\Scripts\python.exe`.
- Bản Python 3.12 do uv tải (`AppData\Roaming\uv\python\...`) **không có chữ ký số**. SAC đánh giá file không ký bằng danh tiếng trên cloud; kết quả có thể đổi theo thời điểm, nên có hôm chạy được, có hôm không. Nhật ký còn có đợt chặn ngày 15/10, 19/10, 23/10.

**Xử lý.** Dùng Python 3.12 bản python.org (có chữ ký Python Software Foundation), không tắt SAC.
```powershell
winget install -e --id Python.Python.3.12 --scope user
uv venv --clear --python "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
uv sync
uv run python -c "import psycopg2, yaml, openpyxl; print('OK')"
```
Thêm vào `pyproject.toml` để uv không quay lại bản không ký:
```toml
[tool.uv]
python-preference = "only-system"
```
Lưu ý: đoạn TOML này phải ghi vào file, không gõ vào PowerShell (lỗi `Unable to find type [tool.uv]`).

Các thư viện có file `.pyd` không ký (`psycopg2`) chạy bình thường, không bị SAC chặn.

### 1.3 Sự cố: sai mật khẩu PostgreSQL

**Dấu hiệu.** `FATAL: password authentication failed for user "postgres"`.

**Chẩn đoán.** `.env` được đọc đúng (độ dài 6 ký tự, không dính nháy, không khoảng trắng); mật khẩu trong `.env` không phải mật khẩu thật của user `postgres` trên server.

**Xử lý.** Sửa `FINOVA_PG_PASSWORD` trong `.env` cho đúng. Mật khẩu ở `finova-dbt/profiles.yml` và `~/.dbt/profiles.yml` phải khớp, nếu không `dbt` gặp đúng lỗi này.

Kiểm nhanh bằng psql:
```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -h 127.0.0.1 -p 5432 -U postgres -d cap_mg_phucnd -c "select current_user;"
```

---

## 2. Nạp landing

```powershell
uv run --env-file .env python -m loader.load   # toàn bộ manifest
```
Tham số khác: `--as-of-date YYYY-MM-DD` (cutoff 00:00 ngày D+1 giờ VN), `--base-dir`.

### Kết quả đối soát

| Chỉ số | Kết quả |
|---|---|
| Lô manifest / lô trong `ctrl.batch_log` | 104 / 104, không thiếu, không trùng `batch_id` |
| `LOADED` | 61 lô, 5.939 dòng |
| `SKIPPED_DUP / DUP_CONTENT` | 43 lô, 3.322 dòng (bản chụp FLEX gửi lại y hệt; có `duplicate_of_batch_id`) |
| Tổng | 9.261 = tổng `row_count` của manifest |
| `ctrl.load_reject`, `ctrl.schema_drift` | 0, 0 |
| `event_ts` NULL ở landing | 0 trên 6 bảng |
| `ctrl.source_system` | 3 nguồn `finova_app`, `flex`, `manual`, `is_simulated_ts = true` |

Truy vấn đã dùng:
```sql
select source_table, status, reason_code, count(*), sum(row_count_declared), sum(rows_loaded)
from ctrl.batch_log group by 1, 2, 3 order by 1, 2, 3;

select count(*), count(distinct batch_id), count(*) filter (where event_ts is null)
from landing.flex_broker;   -- lặp cho 6 bảng
```

---

## 3. Build và kiểm staging

```powershell
$dbt = @("--project-dir", "finova-dbt", "--profiles-dir", "finova-dbt")
uv run --env-file .env dbt debug @dbt
uv run --env-file .env dbt seed @dbt
uv run --env-file .env dbt build --selector cap_mg_staging @dbt
uv run --env-file .env pytest -q
```

Bẫy: cờ `-q` của dbt là cờ toàn cục, phải đặt trước lệnh con (`dbt -q run`), đặt sau (`dbt run -q`) thì dbt báo lỗi mà không in nội dung.

### Đối soát landing = hợp lệ + bị loại

| Nguồn | Landing | Hợp lệ | Bị loại | Lý do loại |
|---|---|---|---|---|
| finova_app_events | 653 | 634 | 19 | `DUPLICATE_EVENT` 12 (lô CAP-MG-0060), `KEY_NULL` 4, `ALLCODE_UNKNOWN` 3 |
| flex_broker | 72 | 72 | 0 | |
| flex_reaflnk | 1316 | 1306 | 10 | `INVALID_DATE_RANGE` 10 |
| flex_regrp | 52 | 50 | 2 | `CYCLE_DETECTED` 2 (G5, G6 ở CAP-MG-0061) |
| manual_kpi | 46 | 38 | 8 | `UNAPPROVED_ROW` 6, `FORMULA_ERROR` 2 |
| ref_nav | 3800 | 3800 | 0 | |

Cảnh báo duy nhất: `test_stg_regrp_parent_missing` (DQ-MOCOI), `G7` trỏ tới `CN9` không có, ở lô CAP-MG-0020 và CAP-MG-0025. Cố ý để mức warn.

### Commit lần 1 (nhánh tách từ `main`)

| Commit | Nội dung |
|---|---|
| `62d5ec5` fix(loader) | Hợp đồng nguồn, loader, `thresholds.yaml`, test loader, `pyproject.toml`, cổng 5436 trong `profiles.example.yml` |
| `b001838` feat(staging) | 12 view, macro, `schema.yml`, `sources.yml`, 3 seed, test singular, `test_hash_tz.py` |
| `bd0ade9` docs(mg) | Sổ kỹ thuật, báo cáo cũ, `decisions.md` (khóa môi giới phương án A) |

Không commit: `.env.example` (bản trên máy có mật khẩu), `finova-dbt/.user.yml` (ID ẩn danh của dbt, đã thêm vào `finova-dbt/.gitignore`).

---

## 4. Những điểm đã làm rõ

### 4.1 Staging test những gì

Ba lớp: test cột trong `schema.yml` (`not_null` mức error cho khóa băm, hashdiff, mốc thời gian; mức warn cho thuộc tính được phép thiếu), test singular trong `finova-dbt/tests/staging/` (mỗi quy tắc một file, đặt tên theo mã GT-/TC-/DQ-), và pytest `tests/staging/test_hash_tz.py` (cần hai phiên database nên không viết bằng dbt test). Chi tiết ở `docs/matran_test.md`.

### 4.2 Staging đạt chuẩn khi nào

1. `dbt build --selector cap_mg_staging` có ERROR = 0.
2. GT-STG-RECON lệch 0 ở mọi lô.
3. Mỗi dòng bị loại có đúng một `reason_code`.
4. Mọi WARN là quy tắc mức cảnh báo và được giải thích cho D-DQ.
5. Mã băm không đổi theo TimeZone/DateStyle (pytest).
6. Mỗi test có phép thử âm đã đỏ.
7. Công cụ `check_khung.py`, `check_ctrl.py` của gói đề đạt (chưa chạy trong phiên này).

### 4.3 Nạp lại, nạp bù

| Tình huống | Loader xử lý |
|---|---|
| Chạy lại loader (vô tình hoặc theo lịch) | Dòng manifest đã có trong sổ (theo `arrival_seq`) bị bỏ qua: 0 lô |
| Nguồn gửi lại cùng `batch_id` | `SKIPPED_DUP / ALREADY_LOADED` |
| Gửi lại file y hệt, `batch_id` mới | `SKIPPED_DUP / DUP_CONTENT` |
| Lô sửa (nội dung khác) | `LOADED` như lô mới; raw vault quyết định có phiên bản mới không bằng hashdiff |
| Nạp bù theo ngày (`--as-of-date`) | Lô sau mốc chưa vào sổ, lần sau tự nhặt |
| File hỏng, sai số dòng, thiếu file | `REJECTED_BATCH`; lỗi giữa chừng rollback cả lô |

Staging là view nên chạy lại bao nhiêu lần cũng cùng kết quả.

Giới hạn: lô `REJECTED_BATCH` đã vào sổ nên không tự thử lại sau khi sửa file, cần dòng manifest mới. Loader không có tùy chọn xóa rồi nạp lại toàn bộ; muốn làm từ đầu thì dựng lại database.

### 4.4 Vì sao staging còn dòng lặp giữa các lô

Ví dụ: `HO` có 5 dòng giống hệt (cùng `regrp_hk`, `sat_regrp_hd`, `record_hash`) ở 5 lô `flex_regrp`, chỉ khác `batch_id`, `ingested_ts`, `event_ts`. Lý do: `flex_regrp` là bản chụp đầy đủ, mỗi lô gửi cả cây; loader chỉ bỏ lô khi **cả file** trùng.

`flex_regrp`: 50 dòng hợp lệ, 11 khóa, 13 phiên bản.

| Lô | Khác lô trước |
|---|---|
| CAP-MG-0020 | Thêm `G7` (cha `CN9`) |
| CAP-MG-0025 | `G7` đổi hashdiff |
| CAP-MG-0051 | `G4` đổi; `G7` biến mất |
| CAP-MG-0061 | `G5`, `G6` tạo vòng, bị loại |

Staging cố ý không khử trùng giữa các lô (KT-03): cần đủ từng bản chụp để phát hiện khóa biến mất, để đối soát theo lô, và để kết quả không phụ thuộc chạy theo ngày hay full refresh. **Raw vault khử trùng:** hub chỉ chèn khóa chưa có, satellite chỉ chèn khi hashdiff khác phiên bản mới nhất (so với bảng vault, không chỉ trong cửa sổ).

---

## 5. Rà soát lần hai và sửa

### 5.1 Đổi tên nhánh

Đề (Phụ lục A) quy định `feat/cap-<đề>-<tên-ngắn>`.
```powershell
git branch -m feat/staging feat/cap-mg-phucnd
```

### 5.2 Database thử cho phép thử âm

Phép thử âm phải sửa dữ liệu, nên chạy trên bản sao, không đụng database thật.

- `create database ... template cap_mg_phucnd` thất bại khi có phiên khác đang kết nối (công cụ quản lý DB đang mở). Dùng pg_dump/pg_restore thay thế:
  ```powershell
  $env:PGPASSWORD = "<mật khẩu>"
  $bin = "C:\Program Files\PostgreSQL\16\bin"
  & "$bin\psql.exe" -h 127.0.0.1 -p 5432 -U postgres -d postgres -c "create database cap_mg_phucnd_negtest"
  & "$bin\pg_dump.exe" -h 127.0.0.1 -p 5432 -U postgres -d cap_mg_phucnd -Fc -f negtest.dump
  & "$bin\pg_restore.exe" -h 127.0.0.1 -p 5432 -U postgres -d cap_mg_phucnd_negtest negtest.dump
  ```
- Trỏ dbt sang DB thử bằng biến môi trường; biến đặt sẵn thắng giá trị trong `.env`:
  ```powershell
  $env:CAP_DBNAME = "cap_mg_phucnd_negtest"
  uv run --env-file .env dbt build --selector cap_mg_staging @dbt
  Remove-Item Env:CAP_DBNAME   # xong thì bỏ, tránh chạy nhầm
  ```
- Chèn hoặc sửa thẳng landing thì GT-STG-RECON đỏ theo (sổ `batch_log` không khớp) và TC-CAP-MG-EVENTTIME có thể đỏ (`landing.event_ts` do loader tính lúc nạp). Đó là hệ quả của cách thử, không phải lỗi.

### 5.3 Phát hiện và sửa

| Mã | Phát hiện | Sửa |
|---|---|---|
| KT-19 | Hai lô cùng `ingested_ts`, cùng khóa, khác nội dung đều vào view hợp lệ; GT-STG-KEYTS đỏ với code chưa sửa | Macro `stg_batch_dup_cols` gom theo `(ingested_ts, khóa)` thay vì `(batch_id, khóa)` |
| KT-20 | Hỏng nhánh khử trùng thì không test nào đỏ; phép thử âm ghi trong `test_stg_keyts.sql` sai (bỏ riêng nhánh xung đột thì KEYTS vẫn xanh vì nhánh trùng che) | Test mới `test_stg_dedup.sql`: vế `DUP_KEPT_TWICE`, vế `DUP_NOT_IDENTICAL`; sửa mô tả phép thử âm của KEYTS |
| KT-21 | 5 cột có mẫu `null_and_count` trong hợp đồng không được kiểm mẫu; giờ thiết bị sai bị thay bằng `server_ts` mà không có cờ | Macro `stg_code_fmt`, `stg_parse_uint`; cột `is_device_ts_invalid`; test warn `test_stg_attr_nulled.sql` |

Các cột của KT-21: `GRPID` (broker), `PARENTID`, `GRPLEVEL` (regrp), `outcome`, `duration_sec` (events).

### 5.4 Kết quả phép thử âm

| Kịch bản | KEYTS | Dedup | Ghi chú |
|---|---|---|---|
| Xóa nhánh `DUPLICATE_EVENT` (DB thật, rồi trả lại) | PASS | FAIL 12 | RECON cũng PASS: chỉ test mới bắt được |
| Chèn BRK001 khác email vào cùng lô, code nguyên | PASS | PASS | Cả 2 dòng `CONFLICT_IN_BATCH` |
| Như trên, xóa nhánh `CONFLICT_IN_BATCH` | PASS | FAIL 1 | Dòng sau bị loại nhầm `DUPLICATE_ROW` |
| Như trên, xóa thêm nhánh `DUPLICATE_ROW` | FAIL 1 | FAIL 1 | |
| Lô `CAP-MG-9999` cùng `ingested_ts` với CAP-MG-0002, macro mới | PASS | PASS | Cả 2 dòng `CONFLICT_IN_BATCH` |
| Như trên, gom lại theo `batch_id` | FAIL 1 | FAIL 1 | Phép thử âm của KEYTS |
| `GRPID = 'X1'`, `raw_event_ts = '20/04/2026 9h'` | | | `test_stg_attr_nulled` warn 2, `not_null` của `grpid` warn 1, sự kiện có cờ `is_device_ts_invalid` |

Sau khi sửa, trên database thật: `dbt build` PASS 69, WARN 1, ERROR 0; pytest 15 passed; số dòng 12 view không đổi.

### 5.5 Kiểm thêm trên dữ liệu (không cần sửa ở staging)

| Điểm | Số liệu | Tầng xử lý |
|---|---|---|
| Phân công chồng lấn trên cùng tiểu khoản | 12 cặp trong cùng lô | Business Vault (DEC-CAP-MG-OVERLAP) |
| Bẫy BRK017: 4 phân công có `FRDATE` trước `JOINDATE` (AUTOID 20, 65, 161, 185) | Ghép theo lô ra 0 dòng vì broker và reaflnk ở các lô khác nhau | Business Vault, ghép theo hiệu lực |
| NAV | Mỗi lô một `tx_date`, 200 tiểu khoản | Raw vault: satellite theo `(account_hk, tx_date)` |
| Khóa biến mất khỏi bản chụp | Chỉ `G7` từ CAP-MG-0051 | Raw vault (đang chờ chốt cách làm) |
| Cùng `event_id` ở nhiều lô khác nội dung | 0 | Raw vault nên ghi lại nếu xảy ra |
| Ô Excel | Chỉ cột C là số nguyên, còn lại là chuỗi | Loader nên chuẩn hóa ô ngày/số (việc còn mở) |

### Commit lần 2

| Commit | Nội dung |
|---|---|
| `966d20d` fix(staging) | KT-19, KT-20, KT-21: macro, `schema.yml`, `test_stg_dedup.sql`, `test_stg_attr_nulled.sql`, sửa `test_stg_keyts.sql` |
| `187bf73` docs(mg) | README (D-RUNBOOK), `docs/matran_test.md` (D-TEST), sổ kỹ thuật KT-19 đến KT-21 |

---

## 6. Việc còn lại

Danh sách tại thời điểm viết nhật ký, giữ nguyên. Trạng thái 06/11/2026: mục 1, 3, 4, 6 đã xong; mục 2 còn mở (xem `docs/ky_thuat_landing_staging.md`); mục 5 giữ phẳng, ghi ở `docs/pr_description.md`.

1. **Raw vault:** thiết kế đã đề xuất, chờ chốt hai điểm: quan hệ cây và môi giới – nhóm dùng link + esat (Q4) hay thuộc tính trong satellite; ghi nhận khóa biến mất bằng view staging dẫn xuất + `sts_*` (T-STS). Cần thêm runner (cửa sổ `lo_ts`/`hi_ts` từ `ctrl.batch_run`, T-GUARD) và seed `ref_bkcc`.
2. **Loader:** chuẩn hóa ô Excel dạng ngày và số trước khi ghi landing, commit riêng.
3. **D-DQ:** bảng `dq_*` và `docs/chatluong.md` từ các view `__rejected` và `test_stg_attr_nulled`.
4. **README ≤ 5 lệnh** (Phụ lục A): gộp lại khi có runner.
5. **Cấu trúc thư mục:** Phụ lục A xếp staging theo `models/staging/<nguồn>/`; hiện đang phẳng. Tên yml nên theo `_<thư mục>__models.yml`.
6. Chạy lại trên máy thật các phép thử âm KT-07 còn ghi kết quả môi trường thay thế; chạy `check_khung.py --dbt --json` ghi `evidence/khung.json`.
7. Dọn dẹp:
   - `.env.example` trên máy đang có mật khẩu, chưa commit; trả về bản repo bằng `git restore .env.example`.
   - Database `cap_mg_phucnd_negtest` đã xóa ngày 05/11/2026 sau khi xong các phép thử âm.
   - Tên tác giả commit đang là `unknown`; đặt bằng `git config user.name "<tên>"`.
