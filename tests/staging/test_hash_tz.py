"""
TC-NEN-HASH-TZ (Bảng 24): khóa băm và hash_diff của staging không đổi khi phiên database đổi TimeZone
hay DateStyle. Staging là view nên mỗi lần đọc là tính lại: chỉ cần đọc toàn bộ cột bytea của mọi
view staging dưới hai thiết lập phiên rồi so dấu vân tay.

Chạy sau `dbt build --selector cap_mg_staging` (cần các biến môi trường như loader).
Phép thử âm: trong dv_fmt_val (macros/finova_macros.sql) đổi nhánh timestamptz thành ({{ expr }})::text
-> dbt build lại staging -> test đỏ ở stg_finova_app__events (nhl_broker_event_hd có giờ).
"""

from __future__ import annotations

import os

import psycopg2
import pytest

SESSIONS = {
    "utc_iso": "SET TimeZone = 'UTC'; SET DateStyle = 'ISO, MDY';",
    "hcm_sql_dmy": "SET TimeZone = 'Asia/Ho_Chi_Minh'; SET DateStyle = 'SQL, DMY';",
}

pytestmark = pytest.mark.skipif(
    not os.environ.get("CAP_DBNAME") or not os.environ.get("FINOVA_PG_PASSWORD"),
    reason="Cần CAP_DBNAME, FINOVA_PG_PASSWORD và staging đã build",
)


def _fingerprints(session_sql: str) -> dict[tuple[str, str], str]:
    conn = psycopg2.connect(
        host=os.environ.get("CAP_PGHOST", "127.0.0.1"),
        port=int(os.environ.get("CAP_PGPORT", "5436")),
        dbname=os.environ["CAP_DBNAME"],
        user=os.environ.get("CAP_PGUSER", "postgres"),
        password=os.environ["FINOVA_PG_PASSWORD"],
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SET ROLE finova_dbt;")
            cur.execute(session_sql)
            cur.execute(
                """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = 'staging' AND table_name LIKE 'stg\\_%%' AND data_type = 'bytea'
                ORDER BY 1, 2;
                """
            )
            targets = cur.fetchall()
            result: dict[tuple[str, str], str] = {}
            for table, column in targets:
                cur.execute(
                    f"""
                    SELECT md5(coalesce(string_agg(encode("{column}", 'hex'), ',' ORDER BY batch_id, source_row_no), ''))
                    FROM staging."{table}";
                    """
                )
                result[(table, column)] = cur.fetchone()[0]
            return result
    finally:
        conn.close()


def test_tc_nen_hash_tz_same_under_two_sessions():
    first, second = (_fingerprints(sql) for sql in SESSIONS.values())
    assert first, "Không tìm thấy cột băm nào trong schema staging: đã build staging chưa?"
    diffs = [key for key in first if first[key] != second.get(key)]
    assert not diffs, f"Mã băm đổi theo TimeZone/DateStyle ở: {diffs}"
