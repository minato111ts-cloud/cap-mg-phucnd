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
    port = int(os.environ.get("CAP_PGPORT", "5432"))
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


def resolve_row_event_ts(
    contract: dict[str, Any],
    row_dict: dict[str, str | None],
    commit_ts_dt: datetime | None,
) -> datetime | None:
    """
    Xác định event_ts của dòng hoàn toàn dựa trên cấu hình Hợp đồng nguồn:
      1. Nếu hợp đồng khai báo event_ts theo mốc lô (commit_ts) -> trả về commit_ts_dt.
      2. Nếu hợp đồng khai báo event_ts theo cột của dòng dữ liệu -> kiểm tra biểu thức/cột
         chính và danh sách fallback được khai báo trong hợp đồng.
      3. Nếu không tính được timestamptz hợp lệ -> trả về None (vi phạm INV-T1 -> load_reject).
    """
    event_cfg = contract.get("event_ts", {})
    expr_text = str(event_cfg.get("expr", "")).lower()

    # Trường hợp 1: Hợp đồng quy định lấy theo commit_ts của lô
    if "commit_ts" in expr_text:
        return commit_ts_dt

    # Trường hợp 2: Hợp đồng quy định lấy theo các cột thời gian của bản ghi
    col_positions: list[tuple[int, str]] = []
    for col_info in contract.get("columns", []):
        cname = col_info["name"]
        ctype = str(col_info.get("type", "")).lower()
        if ctype in ("timestamptz", "timestamp", "date", "datetime"):
            pos = expr_text.find(cname.lower())
            if pos != -1:
                col_positions.append((pos, cname))
    col_positions.sort(key=lambda x: x[0])
    candidate_cols: list[str] = [c for _, c in col_positions]

    # Bổ sung các cột trong fallback
    for fb in event_cfg.get("fallback", []):
        fb_str = str(fb).lower()
        fb_positions: list[tuple[int, str]] = []
        for col_info in contract.get("columns", []):
            cname = col_info["name"]
            pos = fb_str.find(cname.lower())
            if pos != -1 and cname not in candidate_cols:
                fb_positions.append((pos, cname))
        fb_positions.sort(key=lambda x: x[0])
        for _, c in fb_positions:
            if c not in candidate_cols:
                candidate_cols.append(c)

    # Thử parse giá trị từ các cột ứng viên theo thứ tự ưu tiên
    for cname in candidate_cols:
        raw_val = row_dict.get(cname)
        parsed = parse_iso_timestamptz(raw_val)
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
    ref_dir: Path | None = None,
) -> None:
    """
    Khởi tạo hạ tầng schema landing & ctrl theo đúng hợp đồng:
      - Đăng ký hệ thống nguồn giả lập thời gian nạp trong ctrl.source_system (INV-T6).
      - Tạo các bảng landing.<source_table> chứa đủ 5 cột hệ thống NOT NULL.
      - Nạp các bảng tham chiếu (nếu có thư mục ref/) vào landing.ref_*.
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

        # 3. Đồng bộ các danh mục tham chiếu trong ref/ vào landing.ref_*
        if ref_dir and ref_dir.exists():
            for ref_csv in sorted(ref_dir.glob("*.csv")):
                ref_tbl = f"ref_{ref_csv.stem.lower()}"
                with ref_csv.open(encoding="utf-8-sig", newline="") as fp:
                    reader = list(csv.reader(fp))
                if not reader:
                    continue
                headers = [h.lstrip("\ufeff").strip().lower() for h in reader[0]]
                col_defs = [sql.SQL("{} text").format(sql.Identifier(h)) for h in headers]
                cur.execute(
                    sql.SQL("CREATE TABLE IF NOT EXISTS landing.{} ({});").format(
                        sql.Identifier(ref_tbl),
                        sql.SQL(", ").join(col_defs),
                    )
                )
                cur.execute(sql.SQL("TRUNCATE TABLE landing.{};").format(sql.Identifier(ref_tbl)))
                data_rows = [r for r in reader[1:] if any(x.strip() for x in r)]
                if data_rows:
                    insert_ref = sql.SQL("INSERT INTO landing.{} ({}) VALUES %s").format(
                        sql.Identifier(ref_tbl),
                        sql.SQL(", ").join(sql.Identifier(h) for h in headers),
                    )
                    execute_values(cur, insert_ref.as_string(conn), data_rows)

    conn.commit()


def process_single_batch(
    conn,
    manifest_row: dict[str, str],
    base_dir: Path,
    contracts: dict[str, dict[str, Any]],
    excel_header_rows: int = 2,
    commit: bool = True,
) -> dict[str, Any]:
    """
    Xử lý nạp một lô đơn lẻ theo quy trình chuẩn của Loader Finova:
      1. Kiểm tra Idempotency (bỏ qua nếu batch_id đã xử lý thành công).
      2. Kiểm tra tính toàn vẹn vật lý (sha256, row_count; lệch -> REJECTED_BATCH).
      3. Phát hiện gửi lặp nội dung (DUP_CONTENT -> SKIPPED_DUP).
      4. Phát hiện trôi cấu trúc (schema_drift -> tự động thêm cột text NULL và ghi log).
      5. Tính toán 5 cột hệ thống NOT NULL; dòng mất event_ts -> ghi ctrl.load_reject.
      6. Ghi dữ liệu vào landing và ghi sổ kiểm toán vào ctrl.batch_log.
    """
    batch_id = manifest_row["batch_id"].strip()
    source_table = manifest_row["source_table"].strip()
    rel_path = manifest_row["file_path"].strip()
    business_date = manifest_row.get("business_date", "").strip() or None
    commit_ts_str = manifest_row.get("commit_ts", "").strip()
    row_count_declared = int(manifest_row["row_count"])
    sha256_declared = manifest_row["sha256"].strip().lower()

    if source_table not in contracts:
        raise ValueError(f"Không tìm thấy Hợp đồng nguồn cho bảng: {source_table}")

    contract = contracts[source_table]
    source_id = contract["source_id"]
    file_path = base_dir / rel_path

    with conn.cursor() as cur:
        cur.execute("SET ROLE finova_loader;")

        # 1. Kiểm tra Idempotency trên batch_id
        cur.execute(
            """
            SELECT log_id, status, reason_code, rows_loaded, rows_rejected
            FROM ctrl.batch_log
            WHERE batch_id = %s AND status IN ('LOADED', 'SKIPPED_DUP')
            ORDER BY log_id DESC
            LIMIT 1;
            """,
            (batch_id,),
        )
        existing = cur.fetchone()
        if existing:
            return {
                "batch_id": batch_id,
                "status": "ALREADY_PROCESSED",
                "previous_status": existing[1],
                "reason_code": existing[2],
                "rows_loaded": existing[3],
                "rows_rejected": existing[4],
            }

        # 2. Kiểm tra tồn tại file và Checksum SHA-256
        if not file_path.exists():
            cur.execute(
                """
                INSERT INTO ctrl.batch_log (
                    batch_id, source_table, business_date, ingested_ts,
                    status, reason_code, row_count_declared, row_count_read,
                    rows_loaded, rows_rejected, sha256_declared, content_hash
                ) VALUES (%s, %s, %s, NULL, 'REJECTED_BATCH', 'FILE_NOT_FOUND', %s, 0, 0, 0, %s, NULL)
                RETURNING log_id;
                """,
                (batch_id, source_table, business_date, row_count_declared, sha256_declared),
            )
            if commit:
                conn.commit()
            return {
                "batch_id": batch_id,
                "status": "REJECTED_BATCH",
                "reason_code": "FILE_NOT_FOUND",
                "rows_loaded": 0,
                "rows_rejected": 0,
            }

        content_hash = compute_file_sha256(file_path)
        if content_hash != sha256_declared:
            cur.execute(
                """
                INSERT INTO ctrl.batch_log (
                    batch_id, source_table, business_date, ingested_ts,
                    status, reason_code, row_count_declared, row_count_read,
                    rows_loaded, rows_rejected, sha256_declared, content_hash
                ) VALUES (%s, %s, %s, NULL, 'REJECTED_BATCH', 'SHA256_MISMATCH', %s, NULL, 0, 0, %s, %s)
                RETURNING log_id;
                """,
                (batch_id, source_table, business_date, row_count_declared, sha256_declared, content_hash),
            )
            if commit:
                conn.commit()
            return {
                "batch_id": batch_id,
                "status": "REJECTED_BATCH",
                "reason_code": "SHA256_MISMATCH",
                "rows_loaded": 0,
                "rows_rejected": 0,
            }

        # 3. Đọc dữ liệu và kiểm tra Số lượng dòng khai báo
        actual_headers, parsed_rows = read_file_records(
            file_path, contract=contract, excel_header_rows=excel_header_rows
        )
        row_count_read = len(parsed_rows)

        if row_count_read != row_count_declared:
            cur.execute(
                """
                INSERT INTO ctrl.batch_log (
                    batch_id, source_table, business_date, ingested_ts,
                    status, reason_code, row_count_declared, row_count_read,
                    rows_loaded, rows_rejected, sha256_declared, content_hash
                ) VALUES (%s, %s, %s, NULL, 'REJECTED_BATCH', 'ROWCOUNT_MISMATCH', %s, %s, 0, 0, %s, %s)
                RETURNING log_id;
                """,
                (
                    batch_id,
                    source_table,
                    business_date,
                    row_count_declared,
                    row_count_read,
                    sha256_declared,
                    content_hash,
                ),
            )
            if commit:
                conn.commit()
            return {
                "batch_id": batch_id,
                "status": "REJECTED_BATCH",
                "reason_code": "ROWCOUNT_MISMATCH",
                "rows_loaded": 0,
                "rows_rejected": 0,
            }

        # 4. Kiểm tra gửi lặp nội dung byte-for-byte (TH-GUILAI / DUP_CONTENT)
        cur.execute(
            """
            SELECT batch_id
            FROM ctrl.batch_log
            WHERE source_table = %s AND content_hash = %s AND status = 'LOADED'
            ORDER BY log_id ASC
            LIMIT 1;
            """,
            (source_table, content_hash),
        )
        dup_of = cur.fetchone()
        if dup_of:
            cur.execute(
                """
                INSERT INTO ctrl.batch_log (
                    batch_id, source_table, business_date, ingested_ts,
                    status, reason_code, row_count_declared, row_count_read,
                    rows_loaded, rows_rejected, sha256_declared, content_hash, detail
                ) VALUES (
                    %s, %s, %s, NULL, 'SKIPPED_DUP', 'DUP_CONTENT', %s, %s,
                    0, 0, %s, %s, %s
                )
                RETURNING log_id;
                """,
                (
                    batch_id,
                    source_table,
                    business_date,
                    row_count_declared,
                    row_count_read,
                    sha256_declared,
                    content_hash,
                    Json({"duplicate_of_batch_id": dup_of[0]}),
                ),
            )
            if commit:
                conn.commit()
            return {
                "batch_id": batch_id,
                "status": "SKIPPED_DUP",
                "reason_code": "DUP_CONTENT",
                "rows_loaded": 0,
                "rows_rejected": 0,
            }

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

            row_event_ts = resolve_row_event_ts(contract, row_dict, ingested_ts_dt)
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
        if new_cols_detected:
            flag_codes.append("SCHEMA_DRIFT")

        cur.execute(
            """
            INSERT INTO ctrl.batch_log (
                batch_id, source_table, business_date, ingested_ts,
                status, reason_code, row_count_declared, row_count_read,
                rows_loaded, rows_rejected, sha256_declared, content_hash,
                flag_codes, detail
            ) VALUES (
                %s, %s, %s, %s,
                'LOADED', NULL, %s, %s,
                %s, %s, %s, %s,
                %s, %s
            )
            RETURNING log_id;
            """,
            (
                batch_id,
                source_table,
                business_date,
                ingested_ts_dt,
                row_count_declared,
                row_count_read,
                rows_loaded,
                rows_rejected,
                sha256_declared,
                content_hash,
                flag_codes,
                Json({"new_columns": [c[0] for c in new_cols_detected]} if new_cols_detected else {}),
            ),
        )
        log_id = cur.fetchone()[0]

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

    if commit:
        conn.commit()
    return {
        "batch_id": batch_id,
        "status": "LOADED",
        "reason_code": None,
        "rows_loaded": rows_loaded,
        "rows_rejected": rows_rejected,
    }


def load_manifest_batches(
    base_dir: Path = DEFAULT_KIT_MG_DIR,
    contracts_dir: Path = DEFAULT_CONTRACTS_DIR,
    cutoff_ts: datetime | None = None,
    batch_id_filter: str | None = None,
    excel_header_rows: int = 2,
) -> list[dict[str, Any]]:
    """
    Nạp các lô từ manifest.csv theo thứ tự arrival_seq:
      - Hỗ trợ lọc theo cutoff_ts để Runner mô phỏng chạy pipeline theo ngày.
      - Hỗ trợ lọc theo batch_id_filter.
    """
    contracts = load_contracts(contracts_dir)
    manifest_path = base_dir / "inbound" / "manifest.csv"
    ref_dir = base_dir / "ref"

    with manifest_path.open(encoding="utf-8-sig", newline="") as fp:
        manifest_rows = list(csv.DictReader(fp))

    manifest_rows.sort(key=lambda r: int(r["arrival_seq"]))

    conn = get_db_connection()
    try:
        ensure_landing_infrastructure(conn, contracts, ref_dir=ref_dir)
        results: list[dict[str, Any]] = []

        for row in manifest_rows:
            if batch_id_filter and row["batch_id"].strip() != batch_id_filter:
                continue
            if cutoff_ts is not None:
                avail_dt = parse_iso_timestamptz(row["available_ts"])
                if avail_dt is None or avail_dt > cutoff_ts:
                    continue

            res = process_single_batch(
                conn=conn,
                manifest_row=row,
                base_dir=base_dir,
                contracts=contracts,
                excel_header_rows=excel_header_rows,
                commit=True,
            )
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
