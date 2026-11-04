"""
TC-CAP-LDZ (Bảng 24, tầng landing): ingested_ts bằng commit_ts. Mỗi lô LOADED trong ctrl.batch_log có ingested_ts bằng
commit_ts của đúng dòng manifest đã nạp (theo arrival_seq trong detail), và mọi dòng landing của lô mang đúng giá trị đó
(INV-T6: hệ thống nguồn giả lập, ingested_ts lấy từ manifest).

Chỉ đọc, chạy trên CAP_DBNAME sau khi loader đã nạp.
    uv run --env-file .env pytest -q tests/loader/test_ingested_ts.py
"""

from __future__ import annotations

import csv
import os

import psycopg2
import pytest
from psycopg2 import sql

from loader.load import DEFAULT_KIT_MG_DIR, parse_iso_timestamptz


def connect():
    conn = psycopg2.connect(
        host=os.environ.get("CAP_PGHOST", "127.0.0.1"),
        port=int(os.environ.get("CAP_PGPORT", "5436")),
        dbname=os.environ["CAP_DBNAME"],
        user=os.environ.get("CAP_PGUSER", "postgres"),
        password=os.environ["FINOVA_PG_PASSWORD"],
    )
    conn.autocommit = True
    return conn


@pytest.fixture(scope="module")
def loaded_batches() -> list[tuple]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("select to_regclass('ctrl.batch_log') is not null")
        if not cur.fetchone()[0]:
            pytest.skip("Chưa có ctrl.batch_log")
        cur.execute("""
            select distinct on (batch_id) batch_id, source_table, ingested_ts, (detail ->> 'arrival_seq')::int
            from ctrl.batch_log
            where status = 'LOADED'
            order by batch_id, log_id desc
        """)
        rows = cur.fetchall()
    if not rows:
        pytest.skip("Loader chưa nạp lô nào")
    return rows


def test_tc_cap_ldz_ingested_ts_equals_commit_ts(loaded_batches):
    with (DEFAULT_KIT_MG_DIR / "inbound" / "manifest.csv").open(encoding="utf-8-sig", newline="") as fp:
        commit_of = {int(r["arrival_seq"]): parse_iso_timestamptz(r["commit_ts"]) for r in csv.DictReader(fp)}

    problems = []
    with connect() as conn, conn.cursor() as cur:
        for batch_id, table, ingested_ts, arrival_seq in loaded_batches:
            commit_ts = commit_of.get(arrival_seq)
            if commit_ts is None or ingested_ts != commit_ts:
                problems.append(f"{batch_id}: batch_log.ingested_ts {ingested_ts} != commit_ts {commit_ts}")
                continue
            cur.execute(sql.SQL("select ingested_ts, count(*) from landing.{} where batch_id = %s group by 1")
                        .format(sql.Identifier(table)), (batch_id,))
            values = cur.fetchall()
            if any(ts != commit_ts for ts, _ in values):
                problems.append(f"{batch_id} ({table}): landing ingested_ts {[ts for ts, _ in values]} != {commit_ts}")
    assert not problems, "\n".join(problems[:20])
    assert len(loaded_batches) > 0
