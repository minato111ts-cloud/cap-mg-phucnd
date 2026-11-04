# Sổ kỹ thuật tầng as-of và Business Vault — CAP-MG

- **Cập nhật:** 03/11/2026
- **Phạm vi:** `models/asof/` (schema `asof`, view), `models/atomic/bv/` (schema `atomic`, incremental), macro `macros/asof/asof.sql`, `macros/bv/bv.sql`, bước as-of và BV của runner.
- **Căn cứ:** Bảng 20, 24, 70, 72, 83 (T-BV), 85 (GT-BV-*), 86, 88; E.5, E.7, E.8.

## Luồng

```
raw vault (atomic) ──> view as-of (asof, lọc ingested_ts ≤ cutoff của phiên) ──> PIT, bridge của ngày D (atomic) ──> Gold
```

Model BV đặt GUC `finova.asof_date`, `finova.asof_cutoff` của ngày D ngay trên connection của nó (pre_hook), đọc view as-of, xóa phần của D rồi chèn lại. Dựng lại ngày D vào lúc nào cũng ra cùng kết quả vì view chỉ thấy điều hệ thống biết tại cutoff(D).

## AB-01: Chỉ dựng view mà BV và Gold của đề cần

| View `asof.*` | Dùng cho |
|---|---|
| `sat_regrp__flex` | Cây ngày D (`parentid`), đường dẫn cây, phạm vi xem |
| `sat_broker_profile__flex` | `broker_key`, `join_date`, `leave_date` (DEC-BROKERKEY, DEC-GAP), nhóm, trạng thái |
| `sat_reaflnk__flex` | Bản REAFLNK as-of D, mọi phân công đã biết (COVER30 cần phân công của từng ngày trong 30 ngày) |
| `link_reaflnk` | Nối phân công với `broker_hk`, `account_hk` |
| `esat_reaflnk__flex` | Phân công hiệu lực tại D: `fr_date ≤ D ≤ to_date` (Bảng 72; quy tắc esat có thời hiệu, Bảng 88) |
| `sat_account_nav_daily__flex` | CAP-MG-BOOKNAV |
| `sat_broker_kpi__manual` | Chỉ tiêu cuộc gọi, P-MG-KPI |
| `nhl_broker_event` | Tương tác 30 ngày, COVER30, cuộc gọi lũy kế quý |

Không dựng: 4 hub (khóa nghiệp vụ đã có trong satellite); `link_regrp_parent`, `esat_regrp_parent__flex` (cùng thông tin với `parentid`, cùng staging, dòng tạo vòng đã bị loại ở staging cho cả hai); `link_broker_regrp`, `esat_broker_regrp__flex` (nhóm lấy từ `grpid` của hồ sơ); 4 bảng `sts_*` (gộp vào view satellite, AB-03).

Tên model là `asof__<bảng raw>`, khai `alias` để trong DB là `asof.<bảng raw>` như ví dụ `from asof.<link hoặc hub>` ở E.5 (dbt không cho hai model trùng tên).

## AB-02: Hàm đọc cutoff của phiên

`asof.cutoff()`, `asof.as_of_date()` (plpgsql, `stable`) đọc GUC; chưa đặt hoặc chuỗi rỗng (sau `reset`, `current_setting` trả `''`) thì `raise exception`, không lấy giờ hiện tại (TC-SLV-NOCUTOFF). Tạo bằng `create or replace function` ở `on-run-start`: mọi lần dbt chạy đều có hàm, DB mới không cần thêm file setup. GUC thì không đặt ở `on-run-start` vì hook đó chỉ chạy trên một connection (E.8, profile 4 thread).

## AB-03: Gộp sts vào view satellite của nguồn bản chụp

Bảng 88 không có quy tắc riêng cho sts. Với nguồn bản chụp đầy đủ, "bản chụp as-of D" là các khóa có trong bản chụp mới nhất ≤ cutoff, nên `asof_latest(..., sts_model=...)` bỏ khóa có trạng thái mới nhất ≤ cutoff là DELETED. Tầng sau không phải nhớ join sts. Ví dụ: `G7` có ở as-of 24/04, không có từ as-of 27/04 (`CAP-MG-0032`).

## AB-04: Runner chỉ dựng view as-of khi thiếu view hoặc full refresh

View không chứa dữ liệu nên không cần dựng mỗi ngày. Nhưng full refresh một model incremental làm dbt `drop ... cascade` bảng cũ, kéo theo view phụ thuộc. Đo trên DB chính 03/11/2026: full refresh riêng `link_reaflnk` (cùng cửa sổ, vẫn 235 dòng) làm mất `asof.link_reaflnk` và `asof.esat_reaflnk__flex` (còn 6/8 view). Runner vì vậy dựng `cap_mg_asof` khi `--full-refresh` hoặc khi thiếu view (so tên file trong `models/asof/` với `information_schema.views`).

## AB-05: Cơ chế T-BV

- `dbt_project.yml`, mục `bv:` khai một lần hai pre_hook (QT-DAY-REBUILD): `asof_session()` đặt GUC của D, `bv_day_delete()` xóa `as_of_date = D` khi bảng đã có.
- `as_of_date`, `cutoff_ts` của mỗi dòng suy từ `var('as_of_date')` (`asof_var_date()`, `asof_var_cutoff()`), độc lập với GUC mà view đọc. GT-BV-PTR so con trỏ với `cutoff_ts` này nên bắt được GUC đặt sai.
- Full refresh: runner dựng lại BV lần lượt từng ngày giao dịch từ 17/04 tới D, ngày đầu kèm `--full-refresh`. Đo 03/11/2026: `runner.run --full-refresh --skip-load` mất 1 phút 25 giây (raw một cửa sổ, as-of, 19 lần BV).
- `cap_mg_raw` loại tag `dv_bv`: `test_bv_ptr` đọc cả satellite raw, chế độ chọn test mặc định (eager) sẽ kéo nó vào bước raw, trước khi BV tồn tại.

## AB-06: Cây của ngày D (`bridge_regrp_ancestor`)

CTE đệ quy đi ngược lên cha từ mỗi đơn vị, mang theo đường đã đi. Chuỗi dừng ở một trong ba chỗ:

| Dừng ở | Nghĩa | Xử lý |
|---|---|---|
| Đơn vị có `parentid` null | Tới gốc | Giữ |
| Đơn vị đã có trong đường đi | Vòng (DQ-VONG) | Ghi dòng tới đơn vị lặp rồi dừng; giữ để TC-CAP-MG-TREE đỏ |
| Cha không có trong cây của D | Mồ côi (DQ-MOCOI) | Theo nhánh, xem dưới (DEC-CAP-MG-ORPHAN) |

Nhánh mồ côi là đơn vị đứng đầu chuỗi (đơn vị có cha không tồn tại) cùng mọi đơn vị dưới nó. Phân hai dạng theo việc có môi giới nào tại D (`asof.sat_broker_profile__flex`, `grpid` thuộc nhánh):

| Dạng | Nguyên nhân thường gặp | Xử lý trong bridge |
|---|---|---|
| Không có môi giới | Đơn vị không có thật, bản sau sửa ngay | Không vào cây ngày đó; không ảnh hưởng số liệu |
| Có môi giới | Nguồn sai mapping cha, số liệu không lên được gốc | Giữ; đơn vị đứng đầu nhánh treo vào nút ảo `UNKNOWN`, `UNKNOWN` treo dưới gốc; mọi dòng của nhánh và của `UNKNOWN` có `is_orphan_branch = true` |

- `UNKNOWN` chỉ xuất hiện ở ngày có nhánh mồ côi được giữ, và chỉ khi cây có gốc; không có gốc thì `UNKNOWN` không thay làm gốc, TC-CAP-MG-TREE đỏ. Khóa là băm của khóa nghiệp vụ dành riêng `UNKNOWN` (`bv_regrp_unknown_hk()`, `macros/bv/bv.sql`), không trùng mã thật vì staging chỉ nhận `HO`, `CN<số>`, `G<số>`.
- Nguồn sửa cha: ngày có bản sửa ≤ cutoff tự nối về cha thật, `UNKNOWN` biến mất. Ngày trước đó giữ `UNKNOWN` (INV-SEM-ASOF, GT-BV-REBUILD: dựng lại ngày cũ cho cùng kết quả).
- Mã cha thiếu (ví dụ `CN9`) vẫn đọc được ở `parentid` của view as-of; cảnh báo vẫn ở `test_stg_regrp_parent_missing`.
- Gold: nhãn "Chưa xác định" cho `UNKNOWN`; cộng dồn theo vị trí trong cây (đơn vị mồ côi cấp chi nhánh sẽ nằm dưới `UNKNOWN`).

Quy tắc không nêu tên đơn vị nào. Vòng có thể xuất hiện ở as-of dù mỗi lô đều không có vòng, vì as-of ghép phiên bản mới nhất của từng đơn vị từ các lô khác nhau; bước chặn vòng giữ cho đệ quy luôn dừng.

Đối chiếu (DB chính, 04/11/2026): as-of 23/04, 24/04 cây 10 đơn vị (`G7 → CN9` không có môi giới nên không vào cây); cha của `G4` là `CN2` ở 29/04, `CN1` ở 04/05; `G5`, `G6` dưới `CN3` ở 06/05.

Kiểm tình huống có số liệu (DB `negtest`, chèn tạm vào raw rồi khôi phục bằng runner full refresh): thêm `G8 → G7` và `BRK024` thuộc `G8` từ 23/04, `G9 → CN99` không môi giới, bản sửa `G8 → CN1` lúc 22:30 ngày 28/04. Kết quả:

| As-of | Nút | Nhánh mồ côi | `G9` |
|---|---|---|---|
| 22/04 | 10 | — | không |
| 23/04, 24/04 | 13 | `G7>UNKNOWN>HO`, `G8>G7>UNKNOWN>HO`, `UNKNOWN>HO` | không |
| 27/04 (`G7` đã xóa) | 12 | `G8>UNKNOWN>HO`, `UNKNOWN>HO` | không |
| 28/04, 29/04 | 11 | — (`G8>CN1>HO`) | không |

`cap_mg_bv` PASS 13 ở cả 6 ngày (TC-CAP-MG-TREE xanh). Phép thử âm TREE (nạp cây có vòng) sau thay đổi vẫn đỏ 4.

## AB-07: Một môi giới mỗi tiểu khoản (`bridge_account_broker`)

Từ `asof.esat_reaflnk__flex`, xếp hạng theo DEC-CAP-MG-OVERLAP: `fr_date` giảm dần, rồi `ingested_ts` của phiên bản, rồi `autoid` (số nếu toàn chữ số, ngược lại so chữ; nguồn không đảm bảo `AUTOID` là số nên không ép `::bigint`). `is_overlap` khi có từ hai môi giới khác nhau cùng hiệu lực. Không lọc `STATUS` (Bảng 72 chỉ dùng khoảng ngày).

Đối chiếu: 3 tiểu khoản chồng lấn mỗi ngày từ 04/05 tới 08/05, đều về `BRK021`; `9994000016` ngày 28/04 là `BRK005`; `9994000001…15` là `BRK003` ngày 08/05, `BRK009` ngày 11/05.

## AB-08: Test as-of bằng pytest

GUC đặt theo connection; dbt data test không có hook để đặt GUC trên connection của test, nên PT-ASOF-SINGLE, PT-NOFUTURE, TC-SLV-NOCUTOFF, TC-CAP-MG-FUTUREEFF ở `tests/asof/test_asof.py` (Bảng 24 cho phép pytest). TC-CAP-MG-BACKDATE cần kết quả lần dựng đầu nên ở `tests/raw` trên DB `_ptfull`: fixture chạy runner từng ngày và chụp `asof.esat_reaflnk__flex` ngay sau mỗi ngày. FUTUREEFF và BACKDATE tự kiểm dữ liệu có tình huống tương ứng, để không xanh suông.

GT-BV-REBUILD dùng lại dấu vân tay của PT-FULL: thêm 4 bảng BV vào `fingerprint()`, so sau 19 lần chạy theo ngày với sau full refresh dựng lại mọi ngày.
