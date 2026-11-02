"""
Bộ kiểm thử tự động pytest cho tầng Landing & Loader (TC-CAP-LDZ-*).
Thiết kế thuần túy theo Đặc tả Khung Finova Capstone v1.5 (Spec-Driven & Contract-Driven):
  - Tuyệt đối KHÔNG hardcode tên bảng cụ thể hoặc giá trị mẫu (IDs, chi nhánh, tiểu khoản) từ dữ liệu thực.
  - Bộ sinh dữ liệu thử nghiệm động (generate_synthetic_batch) tự động đọc siêu dữ liệu từ Hợp đồng nguồn
    (contracts/*.yml) để tổng hợp tệp dữ liệu giả lập cho mọi định dạng vật lý (CSV, JSONL, XLSX).
  - Kiểm thử toàn diện 100% các Bất biến Kiến trúc (Architecture Invariants) và các Phép thử âm tính:
      + TC-CAP-LDZ-01: Bất biến INV-T6 (ctrl.source_system) và 5 cột hệ thống NOT NULL trong landing trên mọi hợp đồng.
      + TC-CAP-LDZ-02: Phép thử âm tính toàn vẹn vật lý (từ chối lô khi sai SHA-256, lệch row_count, mất tệp).
      + TC-CAP-LDZ-03: Bất biến Idempotent khi nạp lại cùng batch_id và phát hiện trùng nội dung (TH-GUILAI).
      + TC-CAP-LDZ-04: Xử lý an toàn khi xảy ra Trôi cấu trúc (Schema Drift) trên hợp đồng bất kỳ.
      + TC-CAP-LDZ-05: Bất biến INV-T1 (cô lập dòng không tính được event_ts vào ctrl.load_reject).
      + TC-CAP-LDZ-06: Truy vết nguồn gốc vật lý cho bảng tính Excel (Mục 7.2: excel_row_no, source_col_map).
      + TC-CAP-LDZ-07: Chứng minh tính độc lập dữ liệu tuyệt đối qua Hợp đồng giả lập động (Mock Contract).
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

# Tự động nạp thư mục gốc của repo vào sys.path để import được loader.*
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import openpyxl
import pytest

from loader.load import (
    DEFAULT_CONTRACTS_DIR,
    DEFAULT_KIT_MG_DIR,
    ensure_landing_infrastructure,
    get_db_connection,
    load_contracts,
    load_thresholds,
    resolve_row_event_ts,
    process_single_batch,
    read_file_records,
)


@pytest.fixture(scope="module")
def contracts() -> dict[str, dict[str, Any]]:
    """Đọc động toàn bộ hợp đồng nguồn từ thư mục contracts/."""
    return load_contracts(DEFAULT_CONTRACTS_DIR)


@pytest.fixture
def db_conn(contracts):
    """Fixture kết nối database, chạy trong transaction với rollback an toàn sau mỗi test."""
    conn = get_db_connection()
    ensure_landing_infrastructure(conn, contracts)
    yield conn
    conn.rollback()
    conn.close()


def generate_synthetic_batch(
    contract: dict[str, Any],
    tmp_path: Path,
    batch_id: str,
    num_rows: int = 1,
    extra_cols: dict[str, str] | None = None,
    corrupt_event_ts: bool = False,
    override_format: str | None = None,
) -> tuple[dict[str, Any], Path]:
    """
    Sinh lô dữ liệu giả lập động hoàn toàn dựa trên siêu dữ liệu của Hợp đồng nguồn:
      - Không phụ thuộc vào dữ liệu thực tế (zero hardcoding of domain values).
      - Hỗ trợ đa hình định dạng: CSV, JSON Lines (.jsonl), Excel (.xlsx).
      - Tự động tính checksum SHA-256 thực tế và số dòng để tạo bản ghi manifest.
    """
    table_name = contract["table"]
    fmt = (override_format or contract.get("format") or "csv").lower()

    rows_data: list[dict[str, Any]] = []
    for r_idx in range(1, num_rows + 1):
        row: dict[str, Any] = {}
        for col_info in contract.get("columns", []):
            cname = col_info["name"]
            ctype = col_info.get("type", "text").lower()

            if corrupt_event_ts and cname.lower() in ("event_ts", "server_ts", "approved_date"):
                row[cname] = "CORRUPT_TIMESTAMP_VALUE"
            elif ctype == "timestamptz":
                row[cname] = f"2026-04-20T10:00:{r_idx % 60:02d}+07:00"
            elif ctype == "date":
                row[cname] = "2026-04-20"
            elif ctype in ("numeric", "integer", "bigint"):
                row[cname] = str(100 * r_idx)
            else:
                row[cname] = f"mock_{cname.lower()}_{r_idx}"

        if extra_cols:
            for ek, ev in extra_cols.items():
                row[ek] = ev
        rows_data.append(row)

    rel_path = Path(f"inbound/{table_name}/{table_name}_{batch_id}.{fmt}")
    full_path = tmp_path / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "csv":
        all_cols = list(rows_data[0].keys()) if rows_data else [c["name"] for c in contract.get("columns", [])]
        with full_path.open("w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=all_cols)
            writer.writeheader()
            writer.writerows(rows_data)

    elif fmt == "jsonl":
        with full_path.open("w", encoding="utf-8") as fp:
            for r in rows_data:
                fp.write(json.dumps(r, ensure_ascii=False) + "\n")

    elif fmt == "xlsx":
        wb = openpyxl.Workbook()
        ws = wb.active
        all_cols = list(rows_data[0].keys()) if rows_data else [c["name"] for c in contract.get("columns", [])]
        header_rows_count = int(contract.get("header_rows", 2))
        if header_rows_count > 1:
            # Dòng 1: Tiêu đề nhóm / khối
            ws.append([f"Group Header {table_name}"] + [""] * (len(all_cols) - 1))
        # Dòng tiêu đề cột chính
        ws.append(all_cols)
        # Dữ liệu
        for r in rows_data:
            ws.append([r.get(c) for c in all_cols])
        wb.save(full_path)

    else:
        raise ValueError(f"Định dạng không được hỗ trợ trong generator: {fmt}")

    sha = hashlib.sha256(full_path.read_bytes()).hexdigest()
    manifest_row = {
        "batch_id": batch_id,
        "source_table": table_name,
        "file_path": str(rel_path),
        "business_date": "2026-04-20",
        "commit_ts": "2026-04-20T22:00:00+07:00",
        "available_ts": "2026-04-20T22:00:00+07:00",
        "row_count": str(num_rows),
        "sha256": sha,
    }
    return manifest_row, full_path


# ==============================================================================
# TC-CAP-LDZ-01: Bất biến Hệ thống (INV-T6 và 5 cột NOT NULL trong Landing)
# ==============================================================================
def test_tc_cap_ldz_01_spec_invariants_system_columns(contracts, db_conn, tmp_path: Path):
    """
    TC-CAP-LDZ-01:
      - INV-T6: Mọi source_id trong hợp đồng phải được đăng ký vào ctrl.source_system với is_simulated_ts = true.
      - INV-T1 / Mục 2.3: Mọi dòng vào landing.<source_table> phải có đủ 5 cột hệ thống NOT NULL
        (source_id, batch_id, ingested_ts, event_ts, record_hash kiểu bytea 32-byte).
      - Kiểm thử tham số hóa trên TOÀN BỘ các hợp đồng nguồn được phát hiện động.
    """
    for table_name, contract in contracts.items():
        source_id = contract["source_id"]

        # 1. Kiểm tra invariant INV-T6 trong bảng điều khiển ctrl.source_system
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT is_simulated_ts, ingested_ts_rule FROM ctrl.source_system WHERE source_id = %s;",
                (source_id,),
            )
            sys_row = cur.fetchone()
            assert sys_row is not None, f"Chưa đăng ký source_system cho {source_id}"
            assert sys_row[0] is True, "INV-T6 vi phạm: is_simulated_ts phải là true"
            assert sys_row[1] == "manifest.commit_ts"

        # 2. Sinh dữ liệu giả lập động và nạp thử
        batch_id = f"TEST-INV01-{table_name.upper()}"
        manifest_row, _ = generate_synthetic_batch(contract, tmp_path, batch_id=batch_id, num_rows=1)

        res = process_single_batch(db_conn, manifest_row, tmp_path, contracts, commit=False)
        assert res["status"] == "LOADED"
        assert res["rows_loaded"] == 1
        assert res["rows_rejected"] == 0

        # 3. Khẳng định tính NOT NULL và độ dài mã băm 32 bytes của 5 cột hệ thống
        with db_conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT source_id, batch_id, ingested_ts, event_ts, record_hash
                FROM landing.{table_name}
                WHERE batch_id = %s;
                """,
                (batch_id,),
            )
            loaded = cur.fetchall()
            assert len(loaded) == 1, f"Không tìm thấy dòng nạp cho {table_name}"
            s_id, b_id, ing_ts, ev_ts, rec_hash = loaded[0]
            assert s_id == source_id
            assert b_id == batch_id
            assert ing_ts is not None, "ingested_ts không được phép NULL"
            assert ev_ts is not None, "event_ts không được phép NULL (vi phạm INV-T1)"
            assert len(bytes(rec_hash)) == 32, "record_hash phải là 32 bytes kiểu bytea (SHA-256 theo QT-HASH)"


# ==============================================================================
# TC-CAP-LDZ-02: Phép thử âm tính toàn vẹn vật lý (Negative Testing)
# ==============================================================================
@pytest.mark.parametrize(
    "corrupt_scenario",
    ["SHA256_MISMATCH", "ROWCOUNT_MISMATCH", "FILE_MISSING"],
)
def test_tc_cap_ldz_02_negative_physical_integrity(
    corrupt_scenario: str, contracts, db_conn, tmp_path: Path
):
    """
    TC-CAP-LDZ-02:
      - Loader bắt buộc so sánh SHA-256 và row_count thực tế trước khi ghi dữ liệu.
      - Lệch checksum, lệch số dòng, hoặc tệp không tồn tại -> REJECTED_BATCH kèm mã lỗi chính xác.
      - Bất biến cốt lõi: Tuyệt đối không có bất kỳ dòng dữ liệu nào lọt vào schema landing.
    """
    # Lấy hợp đồng đầu tiên để kiểm thử
    sample_table = next(iter(contracts.keys()))
    contract = contracts[sample_table]

    batch_id = f"TEST-CORRUPT-{corrupt_scenario}"
    manifest_row, full_path = generate_synthetic_batch(contract, tmp_path, batch_id=batch_id, num_rows=2)

    if corrupt_scenario == "SHA256_MISMATCH":
        manifest_row["sha256"] = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    elif corrupt_scenario == "ROWCOUNT_MISMATCH":
        manifest_row["row_count"] = "9999"
    elif corrupt_scenario == "FILE_MISSING":
        manifest_row["file_path"] = "inbound/non_existent_folder/missing_file.csv"

    res = process_single_batch(db_conn, manifest_row, tmp_path, contracts, commit=False)
    assert res["status"] == "REJECTED_BATCH"
    assert res["reason_code"] == corrupt_scenario
    assert res["rows_loaded"] == 0

    with db_conn.cursor() as cur:
        # Không có dòng nào vào landing
        cur.execute(f"SELECT count(*) FROM landing.{sample_table} WHERE batch_id = %s;", (batch_id,))
        assert cur.fetchone()[0] == 0

        # Ghi nhận sổ kiểm toán ctrl.batch_log
        cur.execute(
            "SELECT status, reason_code FROM ctrl.batch_log WHERE batch_id = %s;",
            (batch_id,),
        )
        log_entry = cur.fetchone()
        assert log_entry == ("REJECTED_BATCH", corrupt_scenario)


# ==============================================================================
# TC-CAP-LDZ-03: Bất biến Idempotency và Trùng lặp nội dung (TH-GUILAI)
# ==============================================================================
def test_tc_cap_ldz_03_idempotency_and_duplicate_content(contracts, db_conn, tmp_path: Path):
    """
    TC-CAP-LDZ-03:
      - Nạp lại cùng một batch_id đã thành công -> SKIPPED_DUP / ALREADY_LOADED: vẫn ghi sổ (Bảng 18),
        không ghi nhân đôi dòng landing.
      - Lô mới mang batch_id khác nhưng nội dung byte trùng lặp nguyên vẹn (TH-GUILAI)
        -> phát hiện qua content_hash -> SKIPPED_DUP với lý do DUP_CONTENT.
    """
    sample_table = next(iter(contracts.keys()))
    contract = contracts[sample_table]

    # Lần 1: Nạp thành công lô ban đầu
    batch_01 = "TEST-IDEMP-01"
    manifest_01, _ = generate_synthetic_batch(contract, tmp_path, batch_id=batch_01, num_rows=1)
    res1 = process_single_batch(db_conn, manifest_01, tmp_path, contracts, commit=False)
    assert res1["status"] == "LOADED"
    assert res1["rows_loaded"] == 1

    # Lần 2: Nạp lại cùng batch_id (Idempotent check)
    res1_replay = process_single_batch(db_conn, manifest_01, tmp_path, contracts, commit=False)
    assert res1_replay["status"] == "SKIPPED_DUP"
    assert res1_replay["reason_code"] == "ALREADY_LOADED"

    # Lần 3: Lô mới khác batch_id nhưng cùng trỏ tới file có nội dung trùng lặp (TH-GUILAI)
    manifest_02 = dict(manifest_01, batch_id="TEST-IDEMP-02-DUP", business_date="2026-04-21")
    res2_dup = process_single_batch(db_conn, manifest_02, tmp_path, contracts, commit=False)
    assert res2_dup["status"] == "SKIPPED_DUP"
    assert res2_dup["reason_code"] == "DUP_CONTENT"

    with db_conn.cursor() as cur:
        cur.execute(
            f"SELECT count(*) FROM landing.{sample_table} WHERE batch_id IN ('TEST-IDEMP-01', 'TEST-IDEMP-02-DUP');"
        )
        assert cur.fetchone()[0] == 1, "Số dòng trong landing phải là 1 (không được nhân đôi)"

        cur.execute(
            "SELECT status, reason_code FROM ctrl.batch_log WHERE batch_id = %s ORDER BY log_id;",
            (batch_01,),
        )
        assert cur.fetchall() == [("LOADED", None), ("SKIPPED_DUP", "ALREADY_LOADED")]


# ==============================================================================
# TC-CAP-LDZ-04: Khả năng chống chịu Trôi cấu trúc (Schema Drift Resilience)
# ==============================================================================
def test_tc_cap_ldz_04_schema_drift_resilience(contracts, db_conn, tmp_path: Path):
    """
    TC-CAP-LDZ-04:
      - Nguồn gửi thêm cột mới ngoài hợp đồng (Schema Drift).
      - Loader tự động thêm cột mới vào landing dạng text NULL, ghi nhận vào ctrl.schema_drift,
        pipeline nạp thành công mà không bị sập (resilience).
    """
    sample_table = next(iter(contracts.keys()))
    contract = contracts[sample_table]

    drift_col_name = "DYNAMIC_DRIFT_ATTR_TEST"
    drift_col_val = "DRIFT_VALUE_12345"

    batch_id = "TEST-DRIFT-DYN"
    manifest_row, _ = generate_synthetic_batch(
        contract,
        tmp_path,
        batch_id=batch_id,
        num_rows=1,
        extra_cols={drift_col_name: drift_col_val},
    )

    res = process_single_batch(db_conn, manifest_row, tmp_path, contracts, commit=False)
    assert res["status"] == "LOADED"
    assert res["rows_loaded"] == 1

    with db_conn.cursor() as cur:
        # Kiểm tra bảng ctrl.schema_drift
        cur.execute(
            """
            SELECT source_table, column_name, landing_type, review_status
            FROM ctrl.schema_drift
            WHERE source_table = %s AND column_name = %s;
            """,
            (sample_table, drift_col_name),
        )
        drift_entry = cur.fetchone()
        assert drift_entry == (sample_table, drift_col_name, "text", "PENDING_REVIEW")

        # Kiểm tra cột mới đã được tạo trong landing và lưu trữ chính xác giá trị
        cur.execute(
            f"SELECT {drift_col_name.lower()} FROM landing.{sample_table} WHERE batch_id = %s;",
            (batch_id,),
        )
        assert cur.fetchone()[0] == drift_col_val


# ==============================================================================
# TC-CAP-LDZ-05: Bất biến INV-T1 Cô lập dòng lỗi mốc thời gian (Load Reject)
# ==============================================================================
def test_tc_cap_ldz_05_inv_t1_load_reject_missing_event_ts(contracts, db_conn, tmp_path: Path):
    """
    TC-CAP-LDZ-05 (INV-T1):
      - Đối với hợp đồng tính event_ts từ dữ liệu bản ghi (ví dụ luồng sự kiện finova_app_events),
        dòng không thể parse được timestamp hợp lệ KHÔNG ĐƯỢC PHÉP vào landing.
      - Dòng đó phải được cô lập vào ctrl.load_reject (EVENT_TS_UNPARSEABLE),
        trong khi các dòng hợp lệ khác trong cùng lô vẫn được nạp bình thường vào landing.
    """
    # Tìm hợp đồng có quy tắc event_ts tính theo dòng dữ liệu (không phải theo commit_ts của lô)
    row_event_contracts = [
        t for t, c in contracts.items()
        if "commit_ts" not in str(c.get("event_ts", {}).get("expr", "")).lower()
    ]
    if not row_event_contracts:
        pytest.skip("Không có hợp đồng nào tính event_ts từ dòng dữ liệu")

    target_table = row_event_contracts[0]
    contract = contracts[target_table]

    # Tạo tệp chứa 1 dòng hợp lệ và 1 dòng hỏng timestamp
    batch_id = "TEST-INV-T1-ISOLATION"
    rel_path = Path(f"inbound/{target_table}/{target_table}_{batch_id}.jsonl")
    full_path = tmp_path / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)

    valid_record: dict[str, Any] = {}
    corrupt_record: dict[str, Any] = {}

    for c in contract.get("columns", []):
        cname = c["name"]
        ctype = c.get("type", "text").lower()
        if ctype == "timestamptz":
            valid_record[cname] = "2026-04-20T10:00:00+07:00"
            corrupt_record[cname] = "INVALID_UNPARSEABLE_TIME_STRING"
        elif ctype == "date":
            valid_record[cname] = "2026-04-20"
            corrupt_record[cname] = "INVALID_DATE_STRING"
        elif ctype in ("numeric", "integer"):
            valid_record[cname] = "100"
            corrupt_record[cname] = "200"
        else:
            valid_record[cname] = f"valid_{cname.lower()}"
            corrupt_record[cname] = f"corrupt_{cname.lower()}"

    lines = [json.dumps(valid_record), json.dumps(corrupt_record)]
    full_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    actual_sha = hashlib.sha256(full_path.read_bytes()).hexdigest()

    manifest_row = {
        "batch_id": batch_id,
        "source_table": target_table,
        "file_path": str(rel_path),
        "business_date": "2026-04-20",
        "commit_ts": "2026-04-20T23:30:00+07:00",
        "available_ts": "2026-04-20T23:30:00+07:00",
        "row_count": "2",
        "sha256": actual_sha,
    }

    res = process_single_batch(db_conn, manifest_row, tmp_path, contracts, commit=False)
    assert res["status"] == "LOADED"
    assert res["rows_loaded"] == 1
    assert res["rows_rejected"] == 1

    with db_conn.cursor() as cur:
        # Chỉ có 1 dòng hợp lệ vào landing
        cur.execute(f"SELECT count(*) FROM landing.{target_table} WHERE batch_id = %s;", (batch_id,))
        assert cur.fetchone()[0] == 1

        # Dòng hỏng được cô lập vào ctrl.load_reject
        cur.execute(
            """
            SELECT source_row_no, reason_code
            FROM ctrl.load_reject
            WHERE batch_id = %s;
            """,
            (batch_id,),
        )
        reject_entry = cur.fetchone()
        assert reject_entry == (2, "EVENT_TS_UNPARSEABLE")


# ==============================================================================
# TC-CAP-LDZ-06: Truy vết nguồn gốc vật lý cho bảng tính Excel (Mục 7.2)
# ==============================================================================
def test_tc_cap_ldz_06_spreadsheet_physical_tracing(contracts, db_conn, tmp_path: Path):
    """
    TC-CAP-LDZ-06:
      - Đối với định dạng bảng tính Excel (.xlsx), Loader bắt buộc lưu trữ siêu dữ liệu truy vết:
          + excel_row_no: Dòng vật lý thực tế trong tệp Excel (tính sau các dòng tiêu đề).
          + source_col_map: Tọa độ ô Excel tương ứng của từng cột (dạng JSONB, ví dụ {"broker_id": "A3"}).
    """
    xlsx_contracts = [
        t for t, c in contracts.items()
        if c.get("format") == "xlsx" or "kpi" in t or c.get("source_id") == "manual"
    ]
    if not xlsx_contracts:
        pytest.skip("Không có hợp đồng nào thuộc định dạng Excel (.xlsx)")

    table_name = xlsx_contracts[0]
    contract = contracts[table_name]

    batch_id = "TEST-EXCEL-TRACING"
    manifest_row, _ = generate_synthetic_batch(
        contract, tmp_path, batch_id=batch_id, num_rows=2, override_format="xlsx"
    )

    res = process_single_batch(db_conn, manifest_row, tmp_path, contracts, commit=False)
    assert res["status"] == "LOADED"
    assert res["rows_loaded"] == 2

    header_rows_count = int(contract.get("header_rows", 2))

    with db_conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT source_row_no, excel_row_no, source_col_map
            FROM landing.{table_name}
            WHERE batch_id = %s
            ORDER BY source_row_no ASC;
            """,
            (batch_id,),
        )
        rows = cur.fetchall()
        assert len(rows) == 2

        # Dòng 1: excel_row_no phải là header_rows_count + 1
        assert rows[0][0] == 1
        assert rows[0][1] == header_rows_count + 1
        col_map_1 = rows[0][2]
        assert isinstance(col_map_1, dict)
        first_col_name = contract["columns"][0]["name"]
        assert col_map_1.get(first_col_name) == f"A{header_rows_count + 1}"

        # Dòng 2: excel_row_no phải là header_rows_count + 2
        assert rows[1][0] == 2
        assert rows[1][1] == header_rows_count + 2
        col_map_2 = rows[1][2]
        assert col_map_2.get(first_col_name) == f"A{header_rows_count + 2}"


# ==============================================================================
# TC-CAP-LDZ-07: Tính Độc lập Dữ liệu Tuyệt đối qua Hợp đồng Giả lập (Mock Contract)
# ==============================================================================
def test_tc_cap_ldz_07_contract_driven_mock_contract(db_conn, tmp_path: Path):
    """
    TC-CAP-LDZ-07:
      - Khởi tạo một Hợp đồng nguồn hoàn toàn mới (Mock Contract) chưa từng xuất hiện trong đề bài.
      - Chứng minh kiến trúc Loader hoạt động tự động 100% dựa trên Hợp đồng và Đặc tả kỹ thuật,
        không phụ thuộc vào bất kỳ giả định hay dữ liệu cứng nào của bài toán CAP-MG.
    """
    mock_contract = {
        "source_id": "test_core_system",
        "table": "test_synthetic_stream",
        "table_kind": "transaction_log",
        "capture_mode": "incremental",
        "format": "csv",
        "business_key": ["txn_uuid"],
        "event_ts": {
            "expr": "commit_ts của lô trong manifest.csv",
            "fallback": [],
        },
        "columns": [
            {"name": "txn_uuid", "type": "text"},
            {"name": "client_code", "type": "text"},
            {"name": "amount_vnd", "type": "numeric"},
        ],
    }

    mock_contracts_dict = {"test_synthetic_stream": mock_contract}

    # 1. Khởi tạo hạ tầng bảng mới trong landing hoàn toàn tự động
    ensure_landing_infrastructure(db_conn, mock_contracts_dict)

    # 2. Sinh dữ liệu và nạp lô
    batch_id = "TEST-MOCK-INDEPENDENT"
    manifest_row, _ = generate_synthetic_batch(
        mock_contract, tmp_path, batch_id=batch_id, num_rows=3, override_format="csv"
    )

    res = process_single_batch(db_conn, manifest_row, tmp_path, mock_contracts_dict, commit=False)
    assert res["status"] == "LOADED"
    assert res["rows_loaded"] == 3

    # 3. Kiểm chứng dữ liệu và 5 cột hệ thống trong bảng landing mới
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT source_id, batch_id, count(*), min(amount_vnd), max(amount_vnd)
            FROM landing.test_synthetic_stream
            WHERE batch_id = %s
            GROUP BY source_id, batch_id;
            """,
            (batch_id,),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "test_core_system"
        assert row[1] == batch_id
        assert row[2] == 3
        assert row[3] == "100"
        assert row[4] == "300"


# ==============================================================================
# TC-CAP-MG-EXCEL (phần loader): đọc đúng file chỉ tiêu thật của gói đề
# ==============================================================================
KPI_REAL_FILES = sorted((DEFAULT_KIT_MG_DIR / "inbound" / "manual").glob("kpi_targets_*.xlsx"))


@pytest.mark.parametrize("xlsx_path", KPI_REAL_FILES, ids=lambda p: p.name)
def test_tc_cap_mg_excel_real_file_headers(contracts, xlsx_path: Path):
    """
    TC-CAP-MG-EXCEL:
      - File thật có tiêu đề hai dòng tiếng Việt, gộp ô C1:E1. Mọi cột của hợp đồng phải ánh xạ được
        qua aliases; nếu không, landing nạp toàn NULL và staging loại hết các dòng.
      - Không cần database: chỉ kiểm read_file_records.
    """
    contract = contracts["manual_kpi"]
    headers, rows = read_file_records(xlsx_path, contract=contract)

    contract_cols = [c["name"] for c in contract["columns"]]
    assert headers == contract_cols
    assert len(rows) == 23  # khớp row_count của manifest

    first = rows[0]
    assert first["_excel_row"] == 3
    assert first["data"]["broker_id"] == "BRK001"
    assert first["data"]["target_aum_bil"] == "10,5"  # landing giữ nguyên văn, staging mới đổi dấu thập phân

    by_broker = {r["data"]["broker_id"]: r["data"] for r in rows}
    assert by_broker["BRK021"]["target_calls"] == "#REF!"  # DQ-CONGTHUC giữ nguyên ở landing
    assert by_broker["BRK012"]["approver"] is None  # DQ-CHUADUYET


@pytest.mark.parametrize("xlsx_path", KPI_REAL_FILES[:1], ids=lambda p: p.name)
def test_tc_cap_mg_excel_negative_single_header_row(contracts, xlsx_path: Path):
    """Phép thử âm của TC-CAP-MG-EXCEL: đọc với một dòng tiêu đề thì không ánh xạ được đủ cột."""
    contract = dict(contracts["manual_kpi"], header_rows=1)
    headers, rows = read_file_records(xlsx_path, contract=contract)

    assert headers != [c["name"] for c in contract["columns"]]
    assert len(rows) != 23


# ==============================================================================
# DQ-TUONGLAI ở landing: event_ts của loader theo đúng quy tắc hợp đồng và ngưỡng cấu hình
# ==============================================================================
def test_event_ts_future_guard_uses_threshold(contracts):
    """
    Giờ thiết bị đi trước server_ts quá ngưỡng thì event_ts = server_ts; trong ngưỡng thì giữ giờ thiết bị.
    Phép thử âm: tăng ngưỡng lên 10 ngày thì dòng lệch 3 ngày không còn bị thay.
    """
    contract = contracts["finova_app_events"]
    row = {"event_ts": "2026-04-30T13:45:38+07:00", "server_ts": "2026-04-27T13:46:07+07:00"}
    near = {"event_ts": "2026-04-27T13:46:05+07:00", "server_ts": "2026-04-27T13:46:07+07:00"}

    fixed = resolve_row_event_ts(contract, row, None, {"event_future_tolerance_minutes": 5})
    assert fixed.isoformat() == "2026-04-27T13:46:07+07:00"
    kept = resolve_row_event_ts(contract, near, None, {"event_future_tolerance_minutes": 5})
    assert kept.isoformat() == "2026-04-27T13:46:05+07:00"

    loose = resolve_row_event_ts(contract, row, None, {"event_future_tolerance_minutes": 10 * 24 * 60})
    assert loose.isoformat() == "2026-04-30T13:45:38+07:00"


def test_thresholds_in_sync_with_dbt_vars():
    """INV-M6: ngưỡng chỉ có một nguồn; dbt_project.yml phải mang cùng giá trị với thresholds.yaml."""
    import yaml

    thresholds = load_thresholds()
    dbt_vars = yaml.safe_load((REPO_ROOT / "finova-dbt" / "dbt_project.yml").read_text(encoding="utf-8"))["vars"]
    for key, value in thresholds.items():
        assert dbt_vars.get(key) == value, f"{key}: thresholds.yaml={value}, dbt_project.yml={dbt_vars.get(key)}"
