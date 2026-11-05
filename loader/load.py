"""
Bộ nạp dữ liệu tầng Landing & ghi sổ vùng Ctrl (D-LOADER).
Thiết kế thuần túy theo Đặc tả Khung Finova Capstone v1.5 (Spec-Driven & Contract-Driven):
  - Tuyệt đối KHÔNG hardcode tên bảng hoặc cấu trúc dữ liệu cụ thể trong mã nguồn Python.
  - Mọi quy tắc băm khóa, thời gian (event_ts), ánh xạ cột, và kiểm tra tính hợp lệ
    đều được phân giải động từ Hợp đồng nguồn `contracts/*.yml` và `manifest.csv`.
  - Tuân thủ các bất biến cốt lõi:
      + INV-T1: Cột hệ thống event_ts NOT NULL; dòng không tính được event_ts vào ctrl.load_reject.
      + INV-T6: Ghi nhận nguồn giả lập thời gian nạp trong ctrl.source_system.
      + QT-HASH: Băm SHA-256 bytea record_hash theo định dạng chuẩn hóa Unicode NFC.
      + TC-CAP-LDZ-*: Chặn file sai checksum/số dòng; bỏ qua trùng lặp nội dung (DUP_CONTENT);
                       xử lý trôi cấu trúc (schema_drift) an toàn không sập pipeline.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import traceback
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import openpyxl
import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json, execute_values
import yaml

from loader.error_log import log_error

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTRACTS_DIR = REPO_ROOT / "contracts"
DEFAULT_THRESHOLDS_PATH = REPO_ROOT / "customers" / "ctcka" / "thresholds.yaml"
# Thư mục đề: biến CAP_MG_KIT_DIR (runner, pytest cũng theo) hoặc --base-dir; mặc định là gói đề giải nén cạnh repo
DEFAULT_KIT_MG_DIR = Path(
    os.environ.get("CAP_MG_KIT_DIR")
    or REPO_ROOT.parent / "finova_capstone_hocvien_v1.5" / "finova_capstone_hocvien" / "CAP-MG"
)
VN_TZ = timezone(timedelta(hours=7))
# Cột kỹ thuật đứng đầu mỗi bảng landing (tên -> kiểu). excel_row_no, source_col_map chỉ có giá trị với bảng tính
LANDING_SYSTEM_COLS = {
    "source_id": "text NOT NULL",
    "batch_id": "text NOT NULL",
    "ingested_ts": "timestamptz NOT NULL",
    "event_ts": "timestamptz NOT NULL",
    "record_hash": "bytea NOT NULL",
    "source_row_no": "integer NOT NULL",
    "excel_row_no": "integer",
    "source_col_map": "jsonb DEFAULT '{}'::jsonb",
}


def normalize_token(s: str | None) -> str:
    """Chuẩn hóa chuỗi để đối sánh tên cột không phân biệt dấu tiếng Việt, ký tự đặc biệt, hoa thường."""
    if not s:
        return ""
    # Chuyển về dạng NFD để tách dấu tiếng Việt rồi loại bỏ dấu
    decomposed = unicodedata.normalize("NFD", str(s).strip().lower())
    without_accents = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    # Thay thế toàn bộ ký tự không phải chữ/số thành dấu gạch dưới
    return re.sub(r"[^a-z0-9]+", "_", without_accents).strip("_")


def landing_column(name: str) -> str:
    """Tên cột trong landing của một cột nguồn; trùng cột kỹ thuật thì thêm tiền tố raw_."""
    low = name.lower()
    return f"raw_{low}" if low in LANDING_SYSTEM_COLS else low


def pg_connect(dbname: str):
    """Kết nối PostgreSQL theo biến môi trường, chưa chuyển role."""
    return psycopg2.connect(
        host=os.environ.get("CAP_PGHOST", "127.0.0.1"),
        port=int(os.environ.get("CAP_PGPORT", "5436")),  # REQ-ENV-07: container finova-pg16-dev nghe 127.0.0.1:5436
        dbname=dbname,
        user=os.environ.get("CAP_PGUSER", "postgres"),
        password=os.environ["FINOVA_PG_PASSWORD"],
    )


def get_db_connection(role: str = "finova_loader", autocommit: bool = False):
    """Tạo kết nối PostgreSQL và chuyển sang role chức năng (mặc định finova_loader) theo ma trận quyền."""
    conn = pg_connect(os.environ["CAP_DBNAME"])
    conn.autocommit = autocommit
    with conn.cursor() as cur:
        cur.execute(sql.SQL("SET ROLE {};").format(sql.Identifier(role)))
    conn.commit()  # SET trong giao dịch bị rollback thì mất: chốt ngay để role giữ suốt phiên
    return conn


def load_contracts(contracts_dir: Path = DEFAULT_CONTRACTS_DIR) -> dict[str, dict[str, Any]]:
    """Đọc động toàn bộ file hợp đồng nguồn YAML từ thư mục contracts/."""
    contracts: dict[str, dict[str, Any]] = {}
    for yml_file in sorted(contracts_dir.glob("*.yml")):
        with yml_file.open(encoding="utf-8") as fp:
            doc = yaml.safe_load(fp)
            if isinstance(doc, dict) and "table" in doc:
                contracts[doc["table"]] = doc
    return contracts


def compute_record_hash(values: list[str | None]) -> bytes:
    """
    Tính mã băm SHA-256 kiểu bytea của một dòng nguồn theo quy ước QT-HASH:
      - NULL hoặc chuỗi rỗng -> '<NULL>'
      - Chuẩn hóa Unicode NFC, nối bằng '||' và băm SHA-256 ra chuỗi bytea 32 bytes.
    """
    parts = ["<NULL>" if v is None or v == "" else unicodedata.normalize("NFC", str(v)) for v in values]
    return hashlib.sha256("||".join(parts).encode("utf-8")).digest()


def parse_iso_timestamptz(val: str | None) -> datetime | None:
    """Parse timestamp có múi giờ theo chuẩn ISO-8601 (mặc định múi giờ VN nếu chuỗi không chứa offset)."""
    s = (val or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=VN_TZ)
        return dt
    except ValueError:
        return None


def cutoff_of(d: date) -> datetime:
    """cutoff(D): hết ngày D, tức 00:00 ngày D+1 giờ Việt Nam (mục 2.1)."""
    nxt = d + timedelta(days=1)
    return datetime(nxt.year, nxt.month, nxt.day, tzinfo=VN_TZ)


def load_thresholds(path: Path = DEFAULT_THRESHOLDS_PATH) -> dict[str, Any]:
    """Đọc ngưỡng nghiệp vụ của tenant (INV-M6); không ghi cứng ngưỡng trong code."""
    with path.open(encoding="utf-8") as fp:
        return yaml.safe_load(fp) or {}


def resolve_row_event_ts(
    contract: dict[str, Any],
    row_dict: dict[str, str | None],
    commit_ts_dt: datetime | None,
    thresholds: dict[str, Any],
) -> datetime | None:
    """
    Xác định event_ts của dòng theo trường máy đọc của Hợp đồng nguồn (mục event_ts):
      1. Có `column`: lấy cột đó; nếu có `future_guard` mà giá trị đi trước cột so sánh quá ngưỡng
         thì dùng cột so sánh (DQ-TUONGLAI); cột chính không parse được thì thử `fallback_columns`.
      2. Không có `column` và expr nói commit_ts: event_ts là commit_ts của lô (bản chụp).
      3. Không tính được timestamptz hợp lệ -> None (INV-T1 -> ctrl.load_reject).
    """
    event_cfg = contract.get("event_ts", {})
    column = event_cfg.get("column")

    if column is None:
        if "commit_ts" in str(event_cfg.get("expr", "")).lower():
            return commit_ts_dt
        raise ValueError(
            f"Hợp đồng {contract.get('table')}: event_ts phải khai `column` hoặc lấy theo commit_ts"
        )

    primary = parse_iso_timestamptz(row_dict.get(column))
    if primary is not None:
        guard = event_cfg.get("future_guard")
        if guard:
            reference = parse_iso_timestamptz(row_dict.get(guard["compare_to"]))
            tolerance = thresholds[guard["tolerance_minutes_key"]]
            if reference is not None and primary > reference + timedelta(minutes=float(tolerance)):
                return reference
        return primary

    for fb_col in event_cfg.get("fallback_columns", []):
        parsed = parse_iso_timestamptz(row_dict.get(fb_col))
        if parsed is not None:
            return parsed
    return None


def resolve_excel_column_name(raw_header: str, contract_columns: list[dict[str, Any]]) -> str:
    """
    Ánh xạ tiêu đề cột từ file Excel sang tên cột chuẩn trong Hợp đồng nguồn:
      - Đối chiếu theo token chuẩn hóa (không phân biệt hoa thường, dấu tiếng Việt, ký tự đặc biệt).
      - Đối chiếu theo thuộc tính aliases khai báo trong Hợp đồng (nếu có).
    """
    norm_raw = normalize_token(raw_header)
    for c in contract_columns:
        if norm_raw in {normalize_token(n) for n in (c["name"], *c.get("aliases", []))}:
            return c["name"]
    return raw_header.strip()


def _text(val: Any) -> str | None:
    """Giá trị nguyên văn dạng chuỗi; rỗng thành None."""
    return None if val is None or str(val) == "" else str(val)


def _read_csv(file_path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    with file_path.open(encoding="utf-8-sig", newline="") as fp:
        reader = csv.reader(fp)
        headers = [h.strip() for h in next(reader, [])]
        rows: list[dict[str, Any]] = []
        for idx, raw_vals in enumerate(reader, start=1):
            if not any(v.strip() for v in raw_vals):
                continue
            data = {h: _text(raw_vals[i]) if i < len(raw_vals) else None for i, h in enumerate(headers)}
            rows.append({"_row_no": idx, "data": data})
    return headers, rows


def _read_jsonl(file_path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    headers: dict[str, None] = {}
    rows: list[dict[str, Any]] = []
    with file_path.open(encoding="utf-8-sig") as fp:
        for line in fp:
            if not line.strip():
                continue
            data = {str(k).strip(): _text(v) for k, v in json.loads(line).items()}
            headers.update(dict.fromkeys(data))
            rows.append({"_row_no": len(rows) + 1, "data": data})
    return list(headers), rows


def _read_xlsx(file_path: Path, contract: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    ws = openpyxl.load_workbook(file_path, data_only=False).active
    header_rows = int(contract["header_rows"])

    # Tiêu đề ở dòng header_rows; ô trống (gộp ô theo chiều dọc) thì lấy ở dòng 1
    headers = []
    for col_idx in range(1, ws.max_column + 1):
        raw_h = ws.cell(header_rows, col_idx).value or ws.cell(1, col_idx).value
        headers.append(resolve_excel_column_name(str(raw_h or f"col_{col_idx}"), contract.get("columns", [])))

    rows: list[dict[str, Any]] = []
    for cells in ws.iter_rows(min_row=header_rows + 1):
        if all(c.value is None or str(c.value).strip() == "" for c in cells):
            continue
        rows.append(
            {
                "_row_no": len(rows) + 1,
                "_excel_row": cells[0].row,
                "_col_map": {h: c.coordinate for h, c in zip(headers, cells)},
                "data": {h: _text(c.value) for h, c in zip(headers, cells)},
            }
        )
    return headers, rows


def read_file_records(file_path: Path, contract: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    """
    Đọc dữ liệu nguyên văn theo định dạng vật lý của file (CSV, JSONL, XLSX):
      - Không sửa đổi giá trị dữ liệu thô (giữ nguyên string hoặc None).
      - Trích xuất siêu dữ liệu truy vết nguồn gốc (source_row_no, source_col_map đối với bảng tính).
    """
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        return _read_csv(file_path)
    if suffix == ".jsonl":
        return _read_jsonl(file_path)
    if suffix == ".xlsx":
        return _read_xlsx(file_path, contract)
    raise ValueError(f"Định dạng tệp không được hỗ trợ: {file_path}")


def ensure_landing_infrastructure(conn, contracts: dict[str, dict[str, Any]]) -> None:
    """
    Khởi tạo hạ tầng schema landing & ctrl theo đúng hợp đồng; người gọi commit:
      - Đăng ký hệ thống nguồn giả lập thời gian nạp trong ctrl.source_system (INV-T6).
      - Tạo các bảng landing.<source_table> chứa đủ 5 cột hệ thống NOT NULL.
    Danh mục ref/ (event_type, org_roles, calendar) là dbt seed, không vào landing:
    landing chỉ chứa lô theo manifest, chỉ thêm dòng và luôn có 5 cột kỹ thuật (INV-T1).
    """
    with conn.cursor() as cur:
        for sid in sorted({c["source_id"] for c in contracts.values() if "source_id" in c}):
            cur.execute(
                """
                INSERT INTO ctrl.source_system (source_id, is_simulated_ts, ingested_ts_rule, note)
                VALUES (%s, true, 'manifest.commit_ts', 'Hệ thống nguồn giả lập ingested_ts từ manifest theo INV-T6')
                ON CONFLICT (source_id) DO NOTHING;
                """,
                (sid,),
            )

        for tbl_name, contract in contracts.items():
            col_defs = [sql.SQL("{} {}").format(sql.Identifier(c), sql.SQL(t)) for c, t in LANDING_SYSTEM_COLS.items()]
            col_defs += [
                sql.SQL("{} text").format(sql.Identifier(landing_column(c["name"])))
                for c in contract.get("columns", [])
            ]
            cur.execute(
                sql.SQL("CREATE TABLE IF NOT EXISTS landing.{} ({});").format(
                    sql.Identifier(tbl_name), sql.SQL(", ").join(col_defs)
                )
            )


def _log_batch(
    cur,
    manifest_row: dict[str, str],
    status: str,
    reason_code: str | None,
    *,
    ingested_ts: datetime | None = None,
    row_count_read: int | None = None,
    rows_loaded: int = 0,
    rows_rejected: int = 0,
    content_hash: str | None = None,
    flag_codes: list[str] | None = None,
    detail: dict[str, Any] | None = None,
) -> int:
    """Ghi một dòng ctrl.batch_log (chỉ thêm dòng). arrival_seq vào detail để biết dòng manifest nào đã xử lý."""
    detail = dict(detail or {})
    if manifest_row.get("arrival_seq"):
        detail["arrival_seq"] = int(manifest_row["arrival_seq"])
    cur.execute(
        """
        INSERT INTO ctrl.batch_log (
            batch_id, source_table, business_date, ingested_ts,
            status, reason_code, row_count_declared, row_count_read,
            rows_loaded, rows_rejected, sha256_declared, content_hash,
            flag_codes, detail
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING log_id;
        """,
        (
            manifest_row["batch_id"].strip(),
            manifest_row["source_table"].strip(),
            manifest_row.get("business_date", "").strip() or None,
            ingested_ts,
            status,
            reason_code,
            int(manifest_row["row_count"]),
            row_count_read,
            rows_loaded,
            rows_rejected,
            manifest_row["sha256"].strip().lower(),
            content_hash,
            flag_codes or [],
            Json(detail),
        ),
    )
    return cur.fetchone()[0]


def build_landing_rows(
    contract: dict[str, Any],
    parsed_rows: list[dict[str, Any]],
    data_columns: list[str],
    batch_id: str,
    ingested_ts: datetime,
    thresholds: dict[str, Any],
) -> tuple[list[tuple[Any, ...]], list[tuple[int, str, str]]]:
    """Tính cột hệ thống cho từng dòng; dòng không tính được event_ts tách sang danh sách load_reject (INV-T1)."""
    valid_rows: list[tuple[Any, ...]] = []
    rejects: list[tuple[int, str, str]] = []
    for item in parsed_rows:
        row_no: int = item["_row_no"]
        row_dict: dict[str, str | None] = item["data"]

        event_ts = resolve_row_event_ts(contract, row_dict, ingested_ts, thresholds)
        if event_ts is None:
            rejects.append((row_no, "EVENT_TS_UNPARSEABLE", json.dumps(row_dict, ensure_ascii=False)))
            continue

        values = [row_dict.get(col) for col in data_columns]
        valid_rows.append(
            (
                contract["source_id"],
                batch_id,
                ingested_ts,
                event_ts,
                psycopg2.Binary(compute_record_hash(values)),
                row_no,
                item.get("_excel_row"),
                Json(item["_col_map"]) if "_col_map" in item else None,
                *values,
            )
        )
    return valid_rows, rejects


def process_single_batch(
    conn,
    manifest_row: dict[str, str],
    base_dir: Path,
    contracts: dict[str, dict[str, Any]],
    commit: bool = True,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Xử lý nạp một lô đơn lẻ theo quy trình chuẩn của Loader Finova:
      1. batch_id đã LOADED -> SKIPPED_DUP / ALREADY_LOADED (vẫn ghi sổ, không thêm dòng landing).
      2. Kiểm tra tính toàn vẹn vật lý (file, sha256, row_count; lệch -> REJECTED_BATCH).
      3. Phát hiện gửi lặp nội dung (SKIPPED_DUP / DUP_CONTENT).
      4. Phát hiện trôi cấu trúc (schema_drift -> tự động thêm cột text NULL và ghi log).
      5. Tính toán 5 cột hệ thống NOT NULL; dòng mất event_ts -> ghi ctrl.load_reject.
      6. Ghi dữ liệu vào landing và ghi sổ kiểm toán vào ctrl.batch_log.
    """
    batch_id = manifest_row["batch_id"].strip()
    source_table = manifest_row["source_table"].strip()
    rel_path = manifest_row["file_path"].strip()
    commit_ts_str = manifest_row.get("commit_ts", "").strip()
    row_count_declared = int(manifest_row["row_count"])
    sha256_declared = manifest_row["sha256"].strip().lower()

    if source_table not in contracts:
        raise ValueError(f"Không tìm thấy Hợp đồng nguồn cho bảng: {source_table}")
    if thresholds is None:
        thresholds = load_thresholds()

    contract = contracts[source_table]
    file_path = base_dir / rel_path

    def finish(
        status: str, reason_code: str | None, rows_loaded: int = 0, rows_rejected: int = 0, detail: str | None = None,
    ) -> dict[str, Any]:
        if commit:
            conn.commit()
        result = {
            "batch_id": batch_id,
            "status": status,
            "reason_code": reason_code,
            "rows_loaded": rows_loaded,
            "rows_rejected": rows_rejected,
        }
        if detail:
            # mô tả lỗi cho ctrl.error_log (load_manifest_batches ghi), chỉ có khi lô bị từ chối
            result["detail"] = detail
        return result

    with conn.cursor() as cur:
        # 1. Nạp lại cùng batch_id: không sinh dòng landing, nhưng mọi lần xử lý đều vào sổ (Bảng 18)
        cur.execute(
            "SELECT log_id FROM ctrl.batch_log WHERE batch_id = %s AND status = 'LOADED';",
            (batch_id,),
        )
        loaded = cur.fetchone()
        if loaded:
            _log_batch(cur, manifest_row, "SKIPPED_DUP", "ALREADY_LOADED", detail={"loaded_log_id": loaded[0]})
            return finish("SKIPPED_DUP", "ALREADY_LOADED")

        # 2. Kiểm tra tồn tại file và Checksum SHA-256
        if not file_path.exists():
            _log_batch(cur, manifest_row, "REJECTED_BATCH", "FILE_MISSING", row_count_read=0)
            return finish("REJECTED_BATCH", "FILE_MISSING", detail=f"không thấy file {rel_path}")

        content_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if content_hash != sha256_declared:
            _log_batch(cur, manifest_row, "REJECTED_BATCH", "SHA256_MISMATCH", content_hash=content_hash)
            return finish("REJECTED_BATCH", "SHA256_MISMATCH",
                          detail=f"sha256 manifest khai {sha256_declared}, file tính được {content_hash}")

        # 3. Đọc dữ liệu và kiểm tra Số lượng dòng khai báo
        actual_headers, parsed_rows = read_file_records(file_path, contract)
        row_count_read = len(parsed_rows)

        if row_count_read != row_count_declared:
            _log_batch(
                cur, manifest_row, "REJECTED_BATCH", "ROWCOUNT_MISMATCH",
                row_count_read=row_count_read, content_hash=content_hash,
            )
            return finish("REJECTED_BATCH", "ROWCOUNT_MISMATCH",
                          detail=f"row_count manifest khai {row_count_declared}, file đếm được {row_count_read}")

        # 4. Kiểm tra gửi lặp nội dung byte-for-byte (TH-GUILAI / DUP_CONTENT): chỉ so với lô LOADED
        # gần nhất của bảng. Bản chụp quay về nội dung của một lô cũ hơn (A -> B -> A, vd regrp CAP-MG-0032
        # bỏ G7 nên trùng lô 17/04) là thay đổi thật, phải nạp để raw vault ghi phiên bản (PT-ABA).
        cur.execute(
            """
            SELECT batch_id, content_hash
            FROM ctrl.batch_log
            WHERE source_table = %s AND status = 'LOADED'
            ORDER BY log_id DESC
            LIMIT 1;
            """,
            (source_table,),
        )
        latest = cur.fetchone()
        if latest is not None and latest[1] == content_hash:
            _log_batch(
                cur, manifest_row, "SKIPPED_DUP", "DUP_CONTENT",
                row_count_read=row_count_read, content_hash=content_hash,
                detail={"duplicate_of_batch_id": latest[0]},
            )
            return finish("SKIPPED_DUP", "DUP_CONTENT")

        # 5. Phát hiện Trôi cấu trúc (Schema Drift): cột lạ tự mở rộng landing thành cột text NULL
        contract_cols = [c["name"] for c in contract.get("columns", [])]
        contract_tokens = {normalize_token(c) for c in contract_cols}
        new_cols = [(h, pos) for pos, h in enumerate(actual_headers, start=1) if normalize_token(h) not in contract_tokens]
        for col_name, _ in new_cols:
            cur.execute(
                sql.SQL("ALTER TABLE landing.{} ADD COLUMN IF NOT EXISTS {} text;").format(
                    sql.Identifier(source_table),
                    sql.Identifier(landing_column(col_name)),
                )
            )

        # Cột của hợp đồng không tìm thấy trong tiêu đề file (ví dụ tiêu đề Excel chưa khai aliases):
        # landing vẫn nạp nhưng cột đó NULL toàn bộ, nên gắn cờ để lộ ra ở ctrl.batch_log
        header_tokens = {normalize_token(h) for h in actual_headers}
        missing_contract_cols = [c for c in contract_cols if normalize_token(c) not in header_tokens]

        # 6. Tính toán các cột hệ thống và phân tách dòng lỗi event_ts (INV-T1)
        ingested_ts_dt = parse_iso_timestamptz(commit_ts_str)
        if ingested_ts_dt is None:
            raise ValueError(f"commit_ts không đúng định dạng timestamp trong manifest: {commit_ts_str}")

        data_columns = list(dict.fromkeys([*contract_cols, *(c for c, _ in new_cols)]))
        valid_rows, rejects = build_landing_rows(
            contract, parsed_rows, data_columns, batch_id, ingested_ts_dt, thresholds
        )

        # 7. Nạp dòng hợp lệ vào bảng landing.<source_table>
        if valid_rows:
            target_cols = [*LANDING_SYSTEM_COLS, *map(landing_column, data_columns)]
            insert_landing_sql = sql.SQL("INSERT INTO landing.{} ({}) VALUES %s").format(
                sql.Identifier(source_table),
                sql.SQL(", ").join(map(sql.Identifier, target_cols)),
            )
            execute_values(cur, insert_landing_sql.as_string(conn), valid_rows)

        # 8. Ghi sổ kiểm toán ctrl.batch_log
        flag_codes: list[str] = []
        batch_detail: dict[str, Any] = {}
        if new_cols:
            flag_codes.append("SCHEMA_DRIFT")
            batch_detail["new_columns"] = [c for c, _ in new_cols]
        if missing_contract_cols:
            flag_codes.append("CONTRACT_COLUMN_MISSING")
            batch_detail["missing_columns"] = missing_contract_cols

        log_id = _log_batch(
            cur, manifest_row, "LOADED", None,
            ingested_ts=ingested_ts_dt, row_count_read=row_count_read,
            rows_loaded=len(valid_rows), rows_rejected=len(rejects),
            content_hash=content_hash, flag_codes=flag_codes, detail=batch_detail,
        )

        # 9. Ghi dòng bị loại vào ctrl.load_reject
        cur.executemany(
            """
            INSERT INTO ctrl.load_reject (
                log_id, batch_id, source_table, source_row_no, reason_code, detail
            ) VALUES (%s, %s, %s, %s, %s, %s);
            """,
            [(log_id, batch_id, source_table, *r) for r in rejects],
        )

        # 10. Ghi nhận cột mới vào ctrl.schema_drift
        cur.executemany(
            """
            INSERT INTO ctrl.schema_drift (
                log_id, source_table, column_name, ordinal_position, landing_type, review_status
            ) VALUES (%s, %s, %s, %s, 'text', 'PENDING_REVIEW')
            ON CONFLICT (source_table, column_name) DO NOTHING;
            """,
            [(log_id, source_table, *c) for c in new_cols],
        )

    return finish("LOADED", None, len(valid_rows), len(rejects))


def report_batch_errors(res: dict[str, Any], manifest_row: dict[str, str]) -> None:
    """
    Ghi lỗi của một lô vào ctrl.error_log: lô bị từ chối (ERROR) và lô có dòng sang ctrl.load_reject (WARN).
    Gọi ở vòng nạp của load_manifest_batches, không gọi trong process_single_batch, để pytest gọi thẳng
    process_single_batch trong giao dịch rollback không ghi sổ lỗi (bảng chỉ thêm dòng) của database thật.
    """
    file_path = manifest_row["file_path"].strip()
    source_table = manifest_row["source_table"].strip()
    if res["status"] == "REJECTED_BATCH":
        log_error(
            "loader", "check_file", res["reason_code"],
            f"Lô {res['batch_id']} ({source_table}) bị từ chối cả lô: {res.get('detail', res['reason_code'])}",
            object_name=file_path, batch_id=res["batch_id"],
        )
    if res["rows_rejected"]:
        log_error(
            "loader", "insert_landing", "LOAD_REJECT",
            f"Lô {res['batch_id']} ({source_table}): {res['rows_rejected']} dòng không tính được event_ts, "
            "không vào landing; chi tiết ở ctrl.load_reject",
            severity="WARN", object_name=file_path, batch_id=res["batch_id"],
        )


def load_manifest_batches(
    base_dir: Path = DEFAULT_KIT_MG_DIR,
    cutoff_ts: datetime | None = None,
) -> list[dict[str, Any]]:
    """
    Nạp các lô từ manifest.csv theo thứ tự arrival_seq:
      - Chỉ xử lý dòng manifest chưa có trong sổ (theo arrival_seq), nên runner gọi mỗi ngày
        không ghi lặp sổ cho các lô đã xử lý; một lô gửi lại (dòng manifest mới cùng batch_id)
        vẫn được xử lý và ghi ALREADY_LOADED hoặc DUP_CONTENT.
      - Hỗ trợ lọc theo cutoff_ts để Runner mô phỏng chạy pipeline theo ngày.
    """
    contracts = load_contracts()
    thresholds = load_thresholds()

    with (base_dir / "inbound" / "manifest.csv").open(encoding="utf-8-sig", newline="") as fp:
        manifest_rows = sorted(csv.DictReader(fp), key=lambda r: int(r["arrival_seq"]))

    if cutoff_ts is not None:
        manifest_rows = [r for r in manifest_rows
                         if (a := parse_iso_timestamptz(r["available_ts"])) is not None and a <= cutoff_ts]

    conn = get_db_connection()
    try:
        ensure_landing_infrastructure(conn, contracts)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT (detail->>'arrival_seq')::int FROM ctrl.batch_log WHERE detail ? 'arrival_seq';"
            )
            processed_seqs = {r[0] for r in cur.fetchall()}
        conn.commit()

        results: list[dict[str, Any]] = []
        for row in manifest_rows:
            if int(row["arrival_seq"]) in processed_seqs:
                continue

            try:
                res = process_single_batch(conn, row, base_dir, contracts, thresholds=thresholds)
            except Exception:
                # Lỗi giữa chừng: hủy toàn bộ lô (kể cả ALTER TABLE của schema drift), ghi lỗi rồi dừng.
                # error_log dùng kết nối riêng nên dòng lỗi không bị rollback theo lô.
                conn.rollback()
                log_error("loader", "process_batch", "EXCEPTION", traceback.format_exc(),
                          object_name=row["file_path"].strip(), batch_id=row["batch_id"].strip())
                raise
            report_batch_errors(res, row)
            results.append(res)
        return results
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Finova Capstone Loader (D-LOADER)")
    parser.add_argument("--base-dir", type=Path, default=DEFAULT_KIT_MG_DIR,
                        help="Thư mục đề chứa inbound/ (mặc định: CAP_MG_KIT_DIR, hoặc gói đề cạnh repo)")
    parser.add_argument("--as-of-date", type=date.fromisoformat, default=None,
                        help="Ngày nghiệp vụ D (YYYY-MM-DD): chỉ nạp lô có available_ts <= cutoff(D)")
    args = parser.parse_args()

    results = load_manifest_batches(
        base_dir=args.base_dir,
        cutoff_ts=cutoff_of(args.as_of_date) if args.as_of_date else None,
    )

    print(
        f"[LOADER] Đã xử lý {len(results)} lô | Thống kê trạng thái: {dict(Counter(r['status'] for r in results))} | "
        f"Tổng số dòng nạp vào landing: {sum(r['rows_loaded'] for r in results)}"
    )


if __name__ == "__main__":
    main()
