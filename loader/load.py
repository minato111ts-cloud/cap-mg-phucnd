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
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import openpyxl
import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json, execute_values
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTRACTS_DIR = REPO_ROOT / "contracts"
DEFAULT_THRESHOLDS_PATH = REPO_ROOT / "customers" / "ctcka" / "thresholds.yaml"
DEFAULT_KIT_MG_DIR = (
    REPO_ROOT.parent
    / "finova_capstone_hocvien_v1.5"
    / "finova_capstone_hocvien"
    / "CAP-MG"
)


def normalize_token(s: str | None) -> str:
    """Chuẩn hóa chuỗi để đối sánh tên cột không phân biệt dấu tiếng Việt, ký tự đặc biệt, hoa thường."""
    if not s:
        return ""
    # Chuyển về dạng NFD để tách dấu tiếng Việt rồi loại bỏ dấu
    decomposed = unicodedata.normalize("NFD", str(s).strip().lower())
    without_accents = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    # Thay thế toàn bộ ký tự không phải chữ/số thành dấu gạch dưới
    return re.sub(r"[^a-z0-9]+", "_", without_accents).strip("_")


def get_db_connection():
    """Tạo kết nối PostgreSQL và chuyển sang role finova_loader theo quy ước ma trận quyền."""
    host = os.environ.get("CAP_PGHOST", "127.0.0.1")
    port = int(os.environ.get("CAP_PGPORT", "5436"))  # REQ-ENV-07: container finova-pg16-dev nghe 127.0.0.1:5436
    dbname = os.environ["CAP_DBNAME"]
    user = os.environ.get("CAP_PGUSER", "postgres")
    conn = psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=os.environ["FINOVA_PG_PASSWORD"],
    )
    conn.autocommit = False
    with conn.cursor() as cur:
        cur.execute("SET ROLE finova_loader;")
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


def compute_file_sha256(file_path: Path) -> str:
    """Tính mã băm SHA-256 hex thực tế của file nguồn."""
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def compute_record_hash(values: list[str | None]) -> bytes:
    """
    Tính mã băm SHA-256 kiểu bytea của một dòng nguồn theo quy ước QT-HASH:
      - NULL hoặc chuỗi rỗng -> '<NULL>'
      - Chuẩn hóa Unicode NFC, nối bằng '||' và băm SHA-256 ra chuỗi bytea 32 bytes.
    """
    formatted_parts: list[str] = []
    for v in values:
        if v is None or v == "":
            formatted_parts.append("<NULL>")
        else:
            formatted_parts.append(unicodedata.normalize("NFC", str(v)))
    payload = "||".join(formatted_parts).encode("utf-8")
    return hashlib.sha256(payload).digest()


VN_TZ = timezone(timedelta(hours=7))


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


def load_thresholds(path: Path = DEFAULT_THRESHOLDS_PATH) -> dict[str, Any]:
    """Đọc ngưỡng nghiệp vụ của tenant (INV-M6); không ghi cứng ngưỡng trong code."""
    with path.open(encoding="utf-8") as fp:
        return yaml.safe_load(fp) or {}


def resolve_row_event_ts(
    contract: dict[str, Any],
    row_dict: dict[str, str | None],
    commit_ts_dt: datetime | None,
    thresholds: dict[str, Any] | None = None,
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
            tolerance = (thresholds or {})[guard["tolerance_minutes_key"]]
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
    clean_raw = raw_header.strip()
    norm_raw = normalize_token(clean_raw)

    for c in contract_columns:
        cname = c["name"]
        # So khớp trực tiếp hoặc qua token chuẩn hóa
        if norm_raw == normalize_token(cname):
            return cname
        # So khớp với danh sách bí danh (aliases) khai báo trong hợp đồng
        for alias in c.get("aliases", []):
            if norm_raw == normalize_token(alias):
                return cname

    return clean_raw


def read_file_records(
    file_path: Path,
    contract: dict[str, Any],
    excel_header_rows: int = 2,
) -> tuple[list[str], list[dict[str, Any]]]:
    """
    Đọc dữ liệu nguyên văn theo định dạng vật lý của file (CSV, JSONL, XLSX):
      - Không sửa đổi giá trị dữ liệu thô (giữ nguyên string hoặc None).
      - Trích xuất siêu dữ liệu truy vết nguồn gốc (source_row_no, source_col_map đối với bảng tính).
    """
    suffix = file_path.suffix.lower()

    if suffix == ".csv":
        with file_path.open(encoding="utf-8-sig", newline="") as fp:
            reader = csv.reader(fp)
            try:
                raw_headers = next(reader)
            except StopIteration:
                return [], []
            headers = [h.lstrip("\ufeff").strip() for h in raw_headers]
            rows: list[dict[str, Any]] = []
            for idx, raw_vals in enumerate(reader, start=1):
                if not any(v.strip() for v in raw_vals):
                    continue
                row_data: dict[str, str | None] = {}
                for c_idx, h in enumerate(headers):
                    val = raw_vals[c_idx] if c_idx < len(raw_vals) else None
                    row_data[h] = None if val is None or val == "" else val
                rows.append({"_row_no": idx, "data": row_data})
            return headers, rows

    if suffix == ".jsonl":
        headers_order: dict[str, None] = {}
        rows = []
        with file_path.open(encoding="utf-8-sig") as fp:
            data_idx = 0
            for line in fp:
                stripped = line.strip()
                if not stripped:
                    continue
                data_idx += 1
                obj = json.loads(stripped)
                row_data = {}
                for k, v in obj.items():
                    clean_k = str(k).strip()
                    headers_order[clean_k] = None
                    row_data[clean_k] = None if v is None or str(v) == "" else str(v)
                rows.append({"_row_no": data_idx, "data": row_data})
        return list(headers_order.keys()), rows

    if suffix == ".xlsx":
        wb = openpyxl.load_workbook(file_path, data_only=False)
        ws = wb.active
        contract_cols = contract.get("columns", [])
        actual_header_rows = int(contract.get("header_rows", excel_header_rows))

        # Xác định dòng tiêu đề chính (hỗ trợ cấu hình header_rows từ hợp đồng)
        headers = []
        for col_idx in range(1, ws.max_column + 1):
            raw_h = ws.cell(actual_header_rows, col_idx).value
            if raw_h is None and actual_header_rows > 1:
                raw_h = ws.cell(1, col_idx).value
            raw_str = str(raw_h or f"col_{col_idx}").strip()
            mapped_h = resolve_excel_column_name(raw_str, contract_cols)
            headers.append(mapped_h)

        rows = []
        data_idx = 0
        for excel_row in range(actual_header_rows + 1, ws.max_row + 1):
            cell_vals = [ws.cell(excel_row, c).value for c in range(1, ws.max_column + 1)]
            if all(v is None or str(v).strip() == "" for v in cell_vals):
                continue
            data_idx += 1
            row_data = {}
            col_map = {}
            for col_idx, h in enumerate(headers, start=1):
                cell = ws.cell(excel_row, col_idx)
                val = cell.value
                row_data[h] = None if val is None or str(val) == "" else str(val)
                col_map[h] = cell.coordinate
            rows.append(
                {
                    "_row_no": data_idx,
                    "_excel_row": excel_row,
                    "_col_map": col_map,
                    "data": row_data,
                }
            )
        return headers, rows

    raise ValueError(f"Định dạng tệp không được hỗ trợ: {file_path}")


def ensure_landing_infrastructure(
    conn,
    contracts: dict[str, dict[str, Any]],
) -> None:
    """
    Khởi tạo hạ tầng schema landing & ctrl theo đúng hợp đồng:
      - Đăng ký hệ thống nguồn giả lập thời gian nạp trong ctrl.source_system (INV-T6).
      - Tạo các bảng landing.<source_table> chứa đủ 5 cột hệ thống NOT NULL.
    Danh mục ref/ (event_type, org_roles, calendar) là dbt seed, không vào landing:
    landing chỉ chứa lô theo manifest, chỉ thêm dòng và luôn có 5 cột kỹ thuật (INV-T1).
    """
    with conn.cursor() as cur:
        cur.execute("SET ROLE finova_loader;")

        # 1. Đăng ký ctrl.source_system
        source_ids = {c["source_id"] for c in contracts.values() if "source_id" in c}
        for sid in sorted(source_ids):
            cur.execute(
                """
                INSERT INTO ctrl.source_system (source_id, is_simulated_ts, ingested_ts_rule, note)
                VALUES (%s, true, 'manifest.commit_ts', 'Hệ thống nguồn giả lập ingested_ts từ manifest theo INV-T6')
                ON CONFLICT (source_id) DO NOTHING;
                """,
                (sid,),
            )

        # 2. Tạo các bảng landing.<source_table>
        for tbl_name, contract in contracts.items():
            is_spreadsheet = contract.get("format") == "xlsx" or any(
                c.get("format") == "xlsx" for c in [contract]
            )
            col_defs = [
                sql.SQL("source_id text NOT NULL"),
                sql.SQL("batch_id text NOT NULL"),
                sql.SQL("ingested_ts timestamptz NOT NULL"),
                sql.SQL("event_ts timestamptz NOT NULL"),
                sql.SQL("record_hash bytea NOT NULL"),
                sql.SQL("source_row_no integer NOT NULL"),
            ]
            # Bổ sung siêu dữ liệu truy vết nguồn gốc cho bảng tính Excel
            col_defs.append(sql.SQL("excel_row_no integer"))
            col_defs.append(sql.SQL("source_col_map jsonb DEFAULT '{}'::jsonb"))

            sys_cols = {"source_id", "batch_id", "ingested_ts", "event_ts", "record_hash", "source_row_no", "excel_row_no", "source_col_map"}
            for cspec in contract.get("columns", []):
                cname = cspec["name"].lower()
                target_col = f"raw_{cname}" if cname in sys_cols else cname
                col_defs.append(sql.SQL("{} text").format(sql.Identifier(target_col)))

            create_stmt = sql.SQL("CREATE TABLE IF NOT EXISTS landing.{} ({});").format(
                sql.Identifier(tbl_name),
                sql.SQL(", ").join(col_defs),
            )
            cur.execute(create_stmt)

    conn.commit()


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


def process_single_batch(
    conn,
    manifest_row: dict[str, str],
    base_dir: Path,
    contracts: dict[str, dict[str, Any]],
    excel_header_rows: int = 2,
    commit: bool = True,
    thresholds: dict[str, Any] | None = None,
    recheck: bool = False,
) -> dict[str, Any]:
    """
    recheck=True: xét lại một lô đã ghi DUP_CONTENT (--recheck-dup); so với lô LOADED liền trước theo arrival_seq,
    và nếu vẫn trùng thì không ghi thêm dòng sổ.

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
    source_id = contract["source_id"]
    file_path = base_dir / rel_path

    def finish(status: str, reason_code: str | None, rows_loaded: int = 0, rows_rejected: int = 0) -> dict[str, Any]:
        if commit:
            conn.commit()
        return {
            "batch_id": batch_id,
            "status": status,
            "reason_code": reason_code,
            "rows_loaded": rows_loaded,
            "rows_rejected": rows_rejected,
        }

    with conn.cursor() as cur:
        cur.execute("SET ROLE finova_loader;")

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
            return finish("REJECTED_BATCH", "FILE_MISSING")

        content_hash = compute_file_sha256(file_path)
        if content_hash != sha256_declared:
            _log_batch(cur, manifest_row, "REJECTED_BATCH", "SHA256_MISMATCH", content_hash=content_hash)
            return finish("REJECTED_BATCH", "SHA256_MISMATCH")

        # 3. Đọc dữ liệu và kiểm tra Số lượng dòng khai báo
        actual_headers, parsed_rows = read_file_records(
            file_path, contract=contract, excel_header_rows=excel_header_rows
        )
        row_count_read = len(parsed_rows)

        if row_count_read != row_count_declared:
            _log_batch(
                cur, manifest_row, "REJECTED_BATCH", "ROWCOUNT_MISMATCH",
                row_count_read=row_count_read, content_hash=content_hash,
            )
            return finish("REJECTED_BATCH", "ROWCOUNT_MISMATCH")

        # 4. Kiểm tra gửi lặp nội dung byte-for-byte (TH-GUILAI / DUP_CONTENT): chỉ so với lô LOADED
        # gần nhất của bảng. Bản chụp quay về nội dung của một lô cũ hơn (A -> B -> A, vd regrp CAP-MG-0032
        # bỏ G7 nên trùng lô 17/04) là thay đổi thật, phải nạp để raw vault ghi phiên bản (PT-ABA).
        if recheck:
            # Lô nạp lại mang log_id mới nhưng vẫn đứng ở vị trí cũ trong chuỗi bản chụp: lô liền trước lấy theo arrival_seq
            cur.execute(
                """
                SELECT batch_id, content_hash
                FROM ctrl.batch_log
                WHERE source_table = %s AND status = 'LOADED' AND (detail->>'arrival_seq')::int < %s
                ORDER BY (detail->>'arrival_seq')::int DESC
                LIMIT 1;
                """,
                (source_table, int(manifest_row["arrival_seq"])),
            )
        else:
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
        dup_of = latest if latest is not None and latest[1] == content_hash else None
        if dup_of and recheck:
            # vẫn trùng lô liền trước: kết luận cũ đúng, sổ đã có dòng DUP_CONTENT của lô này
            return finish("SKIPPED_DUP", "DUP_CONTENT")
        if dup_of:
            _log_batch(
                cur, manifest_row, "SKIPPED_DUP", "DUP_CONTENT",
                row_count_read=row_count_read, content_hash=content_hash,
                detail={"duplicate_of_batch_id": dup_of[0]},
            )
            return finish("SKIPPED_DUP", "DUP_CONTENT")

        # 5. Phát hiện Trôi cấu trúc (Schema Drift)
        contract_cols_norm = {normalize_token(c["name"]): c["name"] for c in contract.get("columns", [])}
        new_cols_detected: list[tuple[str, int]] = []
        for ordinal, h in enumerate(actual_headers, start=1):
            h_norm = normalize_token(h)
            if h_norm not in contract_cols_norm:
                new_cols_detected.append((h, ordinal))
                # Tự động mở rộng schema landing với cột text NULL
                cur.execute(
                    sql.SQL("ALTER TABLE landing.{} ADD COLUMN IF NOT EXISTS {} text;").format(
                        sql.Identifier(source_table),
                        sql.Identifier(h.lower()),
                    )
                )

        # Cột của hợp đồng không tìm thấy trong tiêu đề file (ví dụ tiêu đề Excel chưa khai aliases):
        # landing vẫn nạp nhưng cột đó NULL toàn bộ, nên gắn cờ để lộ ra ở ctrl.batch_log
        actual_headers_norm = {normalize_token(h) for h in actual_headers}
        missing_contract_cols = [
            c["name"] for c in contract.get("columns", [])
            if normalize_token(c["name"]) not in actual_headers_norm
        ]

        # 6. Tính toán các cột hệ thống và phân tách dòng lỗi event_ts (INV-T1)
        ingested_ts_dt = parse_iso_timestamptz(commit_ts_str)
        if ingested_ts_dt is None:
            raise ValueError(f"commit_ts không đúng định dạng timestamp trong manifest: {commit_ts_str}")

        all_data_columns: list[str] = [c["name"] for c in contract.get("columns", [])]
        for new_col_name, _ in new_cols_detected:
            if new_col_name not in all_data_columns:
                all_data_columns.append(new_col_name)

        valid_rows_to_insert: list[tuple[Any, ...]] = []
        load_reject_records: list[tuple[int, str, str]] = []

        for item in parsed_rows:
            row_no: int = item["_row_no"]
            row_dict: dict[str, str | None] = item["data"]

            row_event_ts = resolve_row_event_ts(contract, row_dict, ingested_ts_dt, thresholds)
            if row_event_ts is None:
                load_reject_records.append(
                    (
                        row_no,
                        "EVENT_TS_UNPARSEABLE",
                        json.dumps(row_dict, ensure_ascii=False),
                    )
                )
                continue

            ordered_values: list[str | None] = [row_dict.get(col) for col in all_data_columns]
            rec_hash_bytes = compute_record_hash(ordered_values)

            excel_row_val = item.get("_excel_row")
            col_map_val = Json(item.get("_col_map", {})) if "_col_map" in item else None

            valid_rows_to_insert.append(
                (
                    source_id,
                    batch_id,
                    ingested_ts_dt,
                    row_event_ts,
                    psycopg2.Binary(rec_hash_bytes),
                    row_no,
                    excel_row_val,
                    col_map_val,
                    *ordered_values,
                )
            )

        # 7. Nạp dòng hợp lệ vào bảng landing.<source_table>
        landing_target_cols = [
            "source_id",
            "batch_id",
            "ingested_ts",
            "event_ts",
            "record_hash",
            "source_row_no",
            "excel_row_no",
            "source_col_map",
        ]
        sys_cols = set(landing_target_cols)
        for col in all_data_columns:
            c_low = col.lower()
            landing_target_cols.append(f"raw_{c_low}" if c_low in sys_cols else c_low)

        if valid_rows_to_insert:
            insert_landing_sql = sql.SQL("INSERT INTO landing.{} ({}) VALUES %s").format(
                sql.Identifier(source_table),
                sql.SQL(", ").join(sql.Identifier(c) for c in landing_target_cols),
            )
            execute_values(cur, insert_landing_sql.as_string(conn), valid_rows_to_insert)

        # 8. Ghi sổ kiểm toán ctrl.batch_log
        rows_loaded = len(valid_rows_to_insert)
        rows_rejected = len(load_reject_records)
        flag_codes: list[str] = []
        batch_detail: dict[str, Any] = {}
        if new_cols_detected:
            flag_codes.append("SCHEMA_DRIFT")
            batch_detail["new_columns"] = [c[0] for c in new_cols_detected]
        if missing_contract_cols:
            flag_codes.append("CONTRACT_COLUMN_MISSING")
            batch_detail["missing_columns"] = missing_contract_cols

        log_id = _log_batch(
            cur, manifest_row, "LOADED", None,
            ingested_ts=ingested_ts_dt, row_count_read=row_count_read,
            rows_loaded=rows_loaded, rows_rejected=rows_rejected,
            content_hash=content_hash, flag_codes=flag_codes, detail=batch_detail,
        )

        # 9. Ghi dòng bị loại vào ctrl.load_reject
        for r_no, r_code, r_detail in load_reject_records:
            cur.execute(
                """
                INSERT INTO ctrl.load_reject (
                    log_id, batch_id, source_table, source_row_no, reason_code, detail
                ) VALUES (%s, %s, %s, %s, %s, %s);
                """,
                (log_id, batch_id, source_table, r_no, r_code, r_detail),
            )

        # 10. Ghi nhận cột mới vào ctrl.schema_drift
        for col_name, ordinal_pos in new_cols_detected:
            cur.execute(
                """
                INSERT INTO ctrl.schema_drift (
                    log_id, source_table, column_name, ordinal_position, landing_type, review_status
                ) VALUES (%s, %s, %s, %s, 'text', 'PENDING_REVIEW')
                ON CONFLICT (source_table, column_name) DO NOTHING;
                """,
                (log_id, source_table, col_name, ordinal_pos),
            )

    return finish("LOADED", None, rows_loaded, rows_rejected)


def recheck_dup_batches(
    conn,
    manifest_rows: list[dict[str, str]],
    base_dir: Path,
    contracts: dict[str, dict[str, Any]],
    thresholds: dict[str, Any],
    excel_header_rows: int = 2,
    commit: bool = True,
) -> list[dict[str, Any]]:
    """
    KT-22: xét lại các dòng manifest đã ghi DUP_CONTENT mà batch_id chưa LOADED, theo thứ tự arrival_seq.
    Lô khác lô LOADED liền trước của bảng thì nạp (bản chụp quay về nội dung cũ, A -> B -> A); vẫn trùng thì
    giữ nguyên, không ghi thêm sổ. Chạy lại không đổi gì.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT (s.detail->>'arrival_seq')::int
            FROM ctrl.batch_log s
            WHERE s.reason_code = 'DUP_CONTENT' AND s.detail ? 'arrival_seq'
              AND NOT EXISTS (SELECT 1 FROM ctrl.batch_log x WHERE x.batch_id = s.batch_id AND x.status = 'LOADED');
            """
        )
        dup_seqs = {r[0] for r in cur.fetchall()}
    results: list[dict[str, Any]] = []
    for row in sorted(manifest_rows, key=lambda r: int(r["arrival_seq"])):
        if int(row["arrival_seq"]) not in dup_seqs:
            continue
        results.append(process_single_batch(
            conn=conn, manifest_row=row, base_dir=base_dir, contracts=contracts,
            excel_header_rows=excel_header_rows, commit=commit, thresholds=thresholds, recheck=True,
        ))
    return results


def load_manifest_batches(
    base_dir: Path = DEFAULT_KIT_MG_DIR,
    contracts_dir: Path = DEFAULT_CONTRACTS_DIR,
    cutoff_ts: datetime | None = None,
    batch_id_filter: str | None = None,
    excel_header_rows: int = 2,
    recheck_dup: bool = False,
) -> list[dict[str, Any]]:
    """
    Nạp các lô từ manifest.csv theo thứ tự arrival_seq:
      - Chỉ xử lý dòng manifest chưa có trong sổ (theo arrival_seq), nên runner gọi mỗi ngày
        không ghi lặp sổ cho các lô đã xử lý; một lô gửi lại (dòng manifest mới cùng batch_id)
        vẫn được xử lý và ghi ALREADY_LOADED hoặc DUP_CONTENT.
      - Hỗ trợ lọc theo cutoff_ts để Runner mô phỏng chạy pipeline theo ngày.
      - Hỗ trợ lọc theo batch_id_filter.
      - recheck_dup=True: chỉ xét lại các lô đã ghi DUP_CONTENT (recheck_dup_batches), không nạp lô mới.
    """
    contracts = load_contracts(contracts_dir)
    thresholds = load_thresholds()
    manifest_path = base_dir / "inbound" / "manifest.csv"

    with manifest_path.open(encoding="utf-8-sig", newline="") as fp:
        manifest_rows = list(csv.DictReader(fp))

    manifest_rows.sort(key=lambda r: int(r["arrival_seq"]))

    if batch_id_filter:
        manifest_rows = [r for r in manifest_rows if r["batch_id"].strip() == batch_id_filter]
    if cutoff_ts is not None:
        manifest_rows = [r for r in manifest_rows
                         if (a := parse_iso_timestamptz(r["available_ts"])) is not None and a <= cutoff_ts]

    conn = get_db_connection()
    try:
        ensure_landing_infrastructure(conn, contracts)
        if recheck_dup:
            try:
                return recheck_dup_batches(conn, manifest_rows, base_dir, contracts, thresholds, excel_header_rows)
            except Exception:
                conn.rollback()
                raise
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
                res = process_single_batch(
                    conn=conn,
                    manifest_row=row,
                    base_dir=base_dir,
                    contracts=contracts,
                    excel_header_rows=excel_header_rows,
                    commit=True,
                    thresholds=thresholds,
                )
            except Exception:
                # Lỗi giữa chừng: hủy toàn bộ lô (kể cả ALTER TABLE của schema drift) rồi dừng
                conn.rollback()
                raise
            results.append(res)
        return results
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Finova Capstone Loader (D-LOADER)")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=DEFAULT_KIT_MG_DIR,
        help="Đường dẫn thư mục bài thi chứa inbound/ và ref/",
    )
    parser.add_argument(
        "--contracts-dir",
        type=Path,
        default=DEFAULT_CONTRACTS_DIR,
        help="Đường dẫn thư mục contracts/",
    )
    parser.add_argument(
        "--cutoff",
        type=str,
        default=None,
        help="Mốc cutoff ISO-8601 (chỉ nạp lô có available_ts <= cutoff)",
    )
    parser.add_argument(
        "--as-of-date",
        type=str,
        default=None,
        help="Ngày nghiệp vụ D (YYYY-MM-DD); tự tính cutoff(D) = 00:00 ngày D+1 giờ VN",
    )
    parser.add_argument(
        "--batch-id",
        type=str,
        default=None,
        help="Chỉ định nạp 1 mã batch_id cụ thể",
    )
    parser.add_argument(
        "--recheck-dup",
        action="store_true",
        help="Xét lại các lô đã ghi DUP_CONTENT theo quy tắc KT-22 (chỉ trùng lô LOADED liền trước mới bỏ qua)",
    )
    args = parser.parse_args()

    cutoff_dt: datetime | None = None
    if args.cutoff:
        cutoff_dt = parse_iso_timestamptz(args.cutoff)
        if cutoff_dt is None:
            raise SystemExit(f"Lỗi: --cutoff không đúng định dạng timestamp ISO-8601: {args.cutoff}")
    elif args.as_of_date:
        from datetime import date, timedelta
        d = datetime.strptime(args.as_of_date, "%Y-%m-%d").date()
        next_day = d + timedelta(days=1)
        cutoff_dt = datetime.fromisoformat(f"{next_day.isoformat()}T00:00:00+07:00")

    results = load_manifest_batches(
        base_dir=args.base_dir,
        contracts_dir=args.contracts_dir,
        cutoff_ts=cutoff_dt,
        batch_id_filter=args.batch_id,
        recheck_dup=args.recheck_dup,
    )

    counts: dict[str, int] = {}
    total_loaded = 0
    for r in results:
        st = r["status"]
        counts[st] = counts.get(st, 0) + 1
        if st == "LOADED":
            total_loaded += r["rows_loaded"]

    print(
        f"[LOADER] Đã xử lý {len(results)} lô | Thống kê trạng thái: {counts} | "
        f"Tổng số dòng nạp vào landing: {total_loaded}"
    )


if __name__ == "__main__":
    main()
