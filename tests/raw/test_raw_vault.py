"""
Test thời gian của raw vault (Bảng 86), GT-BV-REBUILD, TC-CAP-MG-BACKDATE và số liệu kiểm trên dữ liệu đề.

PT-FULL, PT-IDEMP, GT-BV-REBUILD, TC-CAP-MG-BACKDATE, T-GUARD dựng một database thử riêng (<CAP_DBNAME>_ptfull, hoặc
PT_DBNAME) từ đầu: bootstrap.sql, ctrl.sql, rồi runner chạy từng ngày giao dịch. Mất vài phút nên chỉ chạy khi RUN_PT_FULL=1:
    $env:RUN_PT_FULL = "1"; uv run --env-file .env pytest -q tests/raw
Không đặt RUN_PT_FULL thì phần số liệu kiểm chạy trên CAP_DBNAME nếu runner đã chạy thành công ở đó, ngược lại bỏ qua.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import psycopg2
import pytest

from runner.run import DEFAULT_FROM, DEFAULT_TO, cutoff_of, trading_days

REPO_DIR = Path(__file__).resolve().parents[2]
DBT_DIR = REPO_DIR / "finova-dbt"

RAW_TABLES = sorted(p.stem for p in (DBT_DIR / "models" / "atomic" / "raw").glob("*.sql"))
BV_TABLES = sorted(p.stem for p in (DBT_DIR / "models" / "atomic" / "bv").glob("*.sql"))
GOLD_TABLES = sorted(p.stem for p in (DBT_DIR / "models" / "gold").glob("*.sql"))
# (schema, bảng) so trong PT-FULL, GT-BV-REBUILD: raw vault, Business Vault và Gold
VAULT_TABLES = [("atomic", t) for t in RAW_TABLES + BV_TABLES] + [("mart", t) for t in GOLD_TABLES]


def connect(dbname: str):
    return psycopg2.connect(
        host=os.environ.get("CAP_PGHOST", "127.0.0.1"),
        port=int(os.environ.get("CAP_PGPORT", "5436")),
        dbname=dbname,
        user=os.environ.get("CAP_PGUSER", "postgres"),
        password=os.environ["FINOVA_PG_PASSWORD"],
    )


def run_sql_file(conn, path: Path) -> None:
    """Chạy file setup bằng psycopg2: bỏ các dòng lệnh riêng của psql (\\encoding, \\set)."""
    sql = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("\\"))
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def env_for(dbname: str) -> dict[str, str]:
    return dict(os.environ, CAP_DBNAME=dbname)


def run_runner(dbname: str, *args: str, module: str = "runner.run") -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", module, *args], cwd=REPO_DIR, env=env_for(dbname),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def run_dbt_raw(dbname: str, lo_ts: str, hi_ts: str) -> None:
    dbt_vars = json.dumps({"lo_ts": lo_ts, "hi_ts": hi_ts, "as_of_date": "2026-05-15"})
    res = subprocess.run(
        [sys.executable, "-m", "dbt.cli.main", "run", "--selector", "cap_mg_raw",
         "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR), "--vars", dbt_vars],
        cwd=REPO_DIR, env=env_for(dbname), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert res.returncode == 0, res.stdout[-3000:]


def fingerprint(dbname: str) -> dict[str, tuple[int, str]]:
    """Số dòng và md5 của toàn bộ nội dung từng bảng raw vault, Business Vault và Gold (kể cả ingested_ts)."""
    out = {}
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute("set timezone = 'UTC'")
        for schema, t in VAULT_TABLES:
            cur.execute(f"select count(*), md5(coalesce(string_agg(t::text, '|' order by t::text), '')) from {schema}.{t} t")
            out[f"{schema}.{t}"] = cur.fetchone()
    return out


def diff(a: dict, b: dict) -> list[str]:
    return [f"{t}: {a.get(t)} != {b.get(t)}" for t in sorted(set(a) | set(b)) if a.get(t) != b.get(t)]


def asof_assignments(dbname: str, d: date, cutoff: datetime | None = None) -> list[tuple]:
    """Phân công hiệu lực tại D (asof.esat_reaflnk__flex) với cutoff(D), hoặc với cutoff cho trước."""
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute("set role finova_dbt")
        cur.execute("select set_config('finova.asof_date', %s, false), set_config('finova.asof_cutoff', %s, false)",
                    (d.isoformat(), (cutoff or cutoff_of(d)).isoformat()))
        cur.execute("select encode(reaflnk_hk, 'hex'), ingested_ts from asof.esat_reaflnk__flex order by 1, 2")
        return cur.fetchall()


@pytest.fixture(scope="module")
def ptfull() -> dict:
    """Dựng DB thử, chạy runner từng ngày; trả tên DB, dấu vân tay sau khi chạy theo ngày, cửa sổ cuối, và kết quả
    as-of của mỗi ngày D chụp ngay sau lần chạy của D (lần dựng đầu, cho TC-CAP-MG-BACKDATE)."""
    if os.environ.get("RUN_PT_FULL") != "1":
        pytest.skip("Đặt RUN_PT_FULL=1 để chạy PT-FULL/PT-IDEMP (dựng DB thử, vài phút)")
    dbname = os.environ.get("PT_DBNAME", os.environ["CAP_DBNAME"] + "_ptfull")
    assert dbname.endswith("_ptfull"), "Chỉ xóa và dựng lại database thử có hậu tố _ptfull"

    admin = connect("postgres")
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f'drop database if exists "{dbname}" with (force)')
        cur.execute(f'create database "{dbname}"')
    admin.close()
    with connect(dbname) as conn:
        run_sql_file(conn, REPO_DIR / "setup" / "bootstrap.sql")
        run_sql_file(conn, REPO_DIR / "setup" / "ctrl.sql")
        run_sql_file(conn, REPO_DIR / "setup" / "ctrl_runner.sql")
        run_sql_file(conn, REPO_DIR / "setup" / "ctrl_log.sql")

    asof_first = {}
    for d in trading_days(DEFAULT_FROM, DEFAULT_TO):
        res = run_runner(dbname, "--from", d.isoformat(), "--to", d.isoformat())
        assert res.returncode == 0, res.stdout[-3000:] + res.stderr[-3000:]
        asof_first[d] = asof_assignments(dbname, d)

    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute("select lo_ts::text, hi_ts::text from ctrl.batch_run where status = 'SUCCESS' order by run_id desc limit 1")
        last_window = cur.fetchone()
    return {"dbname": dbname, "daily": fingerprint(dbname), "last_window": last_window, "asof_first": asof_first}


@pytest.fixture(scope="module")
def raw_db(request) -> str:
    """DB có raw vault dựng bằng runner: DB thử khi RUN_PT_FULL=1, ngược lại CAP_DBNAME nếu runner đã chạy ở đó."""
    if os.environ.get("RUN_PT_FULL") == "1":
        return request.getfixturevalue("ptfull")["dbname"]
    dbname = os.environ["CAP_DBNAME"]
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute("select to_regclass('ctrl.batch_run') is not null and to_regclass('atomic.hub_broker') is not null")
        ready = cur.fetchone()[0]
        if ready:
            cur.execute("select count(*) from ctrl.batch_run where status = 'SUCCESS'")
            ready = cur.fetchone()[0] > 0
    if not ready:
        pytest.skip(f"{dbname} chưa có raw vault dựng bằng runner")
    return dbname


def query(dbname: str, sql: str) -> list[tuple]:
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


# ------------------------------------------------------------------------------
# PT-IDEMP, PT-FULL
# ------------------------------------------------------------------------------
def test_pt_idemp_rerun_windows(ptfull):
    """PT-IDEMP: chạy lại cửa sổ cuối hai lần, rồi một cửa sổ chứa toàn bộ lịch sử (không full refresh): không thêm dòng."""
    dbname = ptfull["dbname"]
    lo_ts, hi_ts = ptfull["last_window"]
    run_dbt_raw(dbname, lo_ts, hi_ts)
    run_dbt_raw(dbname, lo_ts, hi_ts)
    run_dbt_raw(dbname, "-infinity", hi_ts)
    assert diff(ptfull["daily"], fingerprint(dbname)) == []


def test_pt_full_matches_daily(ptfull):
    """PT-FULL: một cửa sổ (-infinity, hi] dựng lại từ đầu cho cùng tập phiên bản như nạp theo ngày.
    GT-BV-REBUILD: full refresh dựng lại PIT, bridge và bảng Gold của mọi ngày khi đã nạp đủ mọi lô, phải ra đúng như
    lần dựng theo ngày (so md5 của hai lần dựng). Phép thử âm: bỏ asof_day_delete khỏi pre_hook -> dòng nhân đôi, đỏ."""
    dbname = ptfull["dbname"]
    res = run_runner(dbname, "--full-refresh", "--skip-load")
    assert res.returncode == 0, res.stdout[-3000:] + res.stderr[-3000:]
    assert diff(ptfull["daily"], fingerprint(dbname)) == []


def test_tc_cap_mg_backdate(ptfull):
    """TC-CAP-MG-BACKDATE (Bảng 70): sau khi đã nạp mọi lô (kể cả phân công lùi hiệu lực), đọc lại phân công hiệu lực
    của từng ngày cũ cho cùng kết quả với lần dựng đầu. Phép thử âm (theo đề): dùng phân công mới nhất cho mọi ngày
    (bỏ điều kiện ingested_ts <= cutoff ở asof_latest) -> đỏ.
    Có ít nhất một ngày mà điều biết sau này khác điều biết lúc cutoff, để test không xanh suông."""
    dbname = ptfull["dbname"]
    first = ptfull["asof_first"]
    changed = [d for d in first if asof_assignments(dbname, d) != first[d]]
    assert changed == []

    final_cutoff = cutoff_of(max(first))
    known_later = [d for d in first if asof_assignments(dbname, d, cutoff=final_cutoff) != first[d]]
    assert known_later, "Dữ liệu không có phân công nào biết sau cutoff của ngày hiệu lực: test không kiểm được gì"


def rejected_truth(dbname: str) -> dict[tuple[str, str, str], int]:
    """Số dòng thật của mọi view __rejected theo (batch_id, view, reason_code)."""
    views = [r[0] for r in query(dbname, """
        select table_name from information_schema.views
        where table_schema = 'staging' and right(table_name, 10) = '__rejected' order by 1""")]
    out = {}
    for v in views:
        for batch_id, reason, n in query(dbname, f"select batch_id, reason_code, count(*) from staging.{v} group by 1, 2"):
            out[(batch_id, v, reason)] = n
    return out


def test_reject_count_matches_rejected_views(ptfull):
    """DEC-ELT-REJECT: ctrl.reject_count khớp view __rejected; theo ngày mỗi lô đếm ở đúng một lần, full refresh đếm lại đủ."""
    dbname = ptfull["dbname"]
    truth = rejected_truth(dbname)
    assert truth, "dữ liệu đề phải có dòng bị loại ở staging"
    daily = query(dbname, """
        select c.batch_id, c.staging_view, c.reason_code, sum(c.row_count)::int, count(distinct c.run_id)::int
        from ctrl.reject_count c join ctrl.batch_run r using (run_id)
        where r.status = 'SUCCESS' and not r.full_refresh
        group by 1, 2, 3""")
    assert {(b, v, rc): n for b, v, rc, n, _ in daily} == truth
    assert {runs for *_, runs in daily} == {1}
    full = query(dbname, """
        select c.batch_id, c.staging_view, c.reason_code, c.row_count
        from ctrl.reject_count c
        where c.run_id = (select max(run_id) from ctrl.batch_run where status = 'SUCCESS' and full_refresh)""")
    assert {(b, v, rc): n for b, v, rc, n in full} == truth


# ------------------------------------------------------------------------------
# Số liệu kiểm trên dữ liệu đề
# ------------------------------------------------------------------------------
def test_runner_daily_runs(ptfull):
    """Runner chạy đủ 19 ngày giao dịch 17/04 -> 15/05, mọi lần SUCCESS."""
    rows = query(ptfull["dbname"], "select status, count(*) from ctrl.batch_run where not full_refresh group by status")
    assert rows == [("SUCCESS", 19)]


def test_runner_no_failed_run(raw_db):
    """Không lần chạy nào FAILED hay còn RUNNING (DB thật có thể chỉ có một lần full refresh)."""
    rows = query(raw_db, "select status, count(*) from ctrl.batch_run group by status")
    assert dict(rows).get("SUCCESS", 0) >= 1, rows
    assert set(dict(rows)) <= {"SUCCESS", "BLOCKED_BY_GUARD"}, rows


def test_sts_regrp_g7_deleted_at_cap_mg_0032(raw_db):
    """G7 vắng khỏi bản chụp regrp từ CAP-MG-0032 (27/04); G5/G6 bị loại CYCLE_DETECTED ở CAP-MG-0061 vẫn là có mặt."""
    rows = query(raw_db, """
        select h.grpid, s.status, b.batch_id
        from atomic.sts_regrp__flex s
        join atomic.hub_regrp h using (regrp_hk)
        join ctrl.batch_log b on b.source_table = 'flex_regrp' and b.status = 'LOADED' and b.ingested_ts = s.ingested_ts
        order by s.ingested_ts, h.grpid
    """)
    assert rows == [("G7", "DELETED", "CAP-MG-0032")]


def test_esat_regrp_parent_g4_switch(raw_db):
    """TH-TAICAUTRUC / PT-ESAT-SWITCH: G4 đổi cha CN2 -> CN1 ở CAP-MG-0051: một dòng đóng, một dòng mở, cùng ingested_ts."""
    rows = query(raw_db, """
        select p.grpid, e.is_active, b.batch_id
        from atomic.esat_regrp_parent__flex e
        join atomic.link_regrp_parent l using (link_regrp_parent_hk)
        join atomic.hub_regrp h on h.regrp_hk = l.regrp_hk
        join atomic.hub_regrp p on p.regrp_hk = l.parent_regrp_hk
        join ctrl.batch_log b on b.source_table = 'flex_regrp' and b.status = 'LOADED' and b.ingested_ts = e.ingested_ts
        where h.grpid = 'G4'
        order by e.ingested_ts, e.is_active
    """)
    assert rows == [("CN2", True, "CAP-MG-0001"), ("CN2", False, "CAP-MG-0051"), ("CN1", True, "CAP-MG-0051")]


def test_cycle_rows_never_reach_vault(raw_db):
    """DEC-CAP-MG-CYCLE: không phiên bản nào của G5/G6 có cha là G6/G5."""
    rows = query(raw_db, """
        select grpid, parentid from atomic.sat_regrp__flex
        where (grpid, parentid) in (('G5', 'G6'), ('G6', 'G5'))
    """)
    assert rows == []


def test_broker_code_reuse_versions(raw_db):
    """DEC-CAP-MG-BROKERKEY: BRK017 một khóa hub, ba phiên bản hồ sơ: người cũ, người cũ nghỉ việc, người mới."""
    rows = query(raw_db, """
        select broker_key, status, leave_date::text
        from atomic.sat_broker_profile__flex where broker_id = 'BRK017' order by ingested_ts
    """)
    assert rows == [
        ("BRK017:2025-05-14", "A", None),
        ("BRK017:2025-05-14", "C", "2026-04-30"),
        ("BRK017:2026-05-11", "A", None),
    ]
    assert query(raw_db, "select count(*) from atomic.hub_broker where broker_id = 'BRK017'") == [(1,)]


# ------------------------------------------------------------------------------
# T-GUARD (chạy cuối vì ghi lô giả vào sổ nạp của DB thử; batch_log không xóa được). Thứ tự các test dưới đây
# là một kịch bản: chặn -> full refresh xử lý -> chặn lô khác -> ACCEPTED cho chạy tiếp.
# ------------------------------------------------------------------------------
def insert_replay_batch(dbname: str, batch_id: str) -> int:
    """Lô giả mang giờ 22/04, nạp sau lần chạy cuối (không có dòng landing)."""
    with connect(dbname) as conn, conn.cursor() as cur:
        cur.execute("set role finova_loader")
        cur.execute("""
            insert into ctrl.batch_log (batch_id, source_table, business_date, ingested_ts, status, detail)
            values (%s, 'flex_regrp', '2026-04-22', '2026-04-22 23:30:00+07', 'LOADED', '{"note": "phép thử âm T-GUARD"}')
            returning log_id
        """, (batch_id,))
        return cur.fetchone()[0]


def last_run(dbname: str) -> tuple:
    return query(dbname, "select run_id, status, error_msg from ctrl.batch_run order by run_id desc limit 1")[0]


def run_last_day(dbname: str) -> subprocess.CompletedProcess:
    return run_runner(dbname, "--from", "2026-05-15", "--to", "2026-05-15", "--skip-load")


def test_t_guard_blocks_replayed_batch(ptfull):
    """T-GUARD: lô LOADED nạp sau lần chạy thành công gần nhất mà mang ingested_ts <= lo_ts thì BLOCKED_BY_GUARD,
    và lô được ghi vào ctrl.guard_block, hiện ở ctrl.v_guard_open."""
    dbname = ptfull["dbname"]
    log_id = insert_replay_batch(dbname, "CAP-MG-REPLAY-TEST")
    res = run_last_day(dbname)
    assert res.returncode == 1
    run_id, status, error_msg = last_run(dbname)
    assert status == "BLOCKED_BY_GUARD"
    assert "CAP-MG-REPLAY-TEST" in error_msg
    assert query(dbname, f"select log_id, batch_id, source_table from ctrl.guard_block where run_id = {run_id}") == [
        (log_id, "CAP-MG-REPLAY-TEST", "flex_regrp")]
    # chạy lại khi chưa xử lý: vẫn chặn, v_guard_open gộp hai lần chặn thành một lô
    assert run_last_day(dbname).returncode == 1
    assert query(dbname, "select log_id, blocked_runs from ctrl.v_guard_open") == [(log_id, 2)]
    out = run_runner(dbname, "list", module="runner.guard")
    assert out.returncode == 0 and "CAP-MG-REPLAY-TEST" in out.stdout and "--full-refresh" in out.stdout


def test_t_guard_full_refresh_resolves_block(ptfull):
    """Full refresh SUCCESS phủ lô bị chặn thì runner ghi FULL_REFRESH; lần chạy sau không bị chặn, vault không đổi."""
    dbname = ptfull["dbname"]
    res = run_runner(dbname, "--full-refresh", "--skip-load", "--to", "2026-05-15")
    assert res.returncode == 0, res.stdout[-3000:] + res.stderr[-3000:]
    fr_run_id = last_run(dbname)[0]
    assert query(dbname, """
        select b.batch_id, r.action, r.resolved_run_id, r.resolved_by
        from ctrl.guard_resolution r join ctrl.batch_log b using (log_id)""") == [
        ("CAP-MG-REPLAY-TEST", "FULL_REFRESH", fr_run_id, "runner")]
    assert query(dbname, "select count(*) from ctrl.v_guard_open") == [(0,)]
    assert run_last_day(dbname).returncode == 0
    assert last_run(dbname)[1] == "SUCCESS"
    # Vault, BV và Gold không đổi; riêng bảng chất lượng báo theo sổ nạp nên có thêm đúng dòng của lô giả ở ngày 22/04
    after = fingerprint(dbname)
    assert diff({k: v for k, v in ptfull["daily"].items() if k != "mart.dq_mg_daily"},
                {k: v for k, v in after.items() if k != "mart.dq_mg_daily"}) == []
    assert after["mart.dq_mg_daily"][0] == ptfull["daily"]["mart.dq_mg_daily"][0] + 1
    assert query(dbname, "select as_of_date::text, rows_landing, reason_code from mart.dq_mg_daily "
                         "where batch_id = 'CAP-MG-REPLAY-TEST'") == [("2026-04-22", 0, None)]


def test_t_guard_accept_lets_run_continue(ptfull):
    """ACCEPTED: người vận hành cho chạy tiếp mà chưa đưa lô vào vault; bắt buộc ghi lý do."""
    dbname = ptfull["dbname"]
    log_id = insert_replay_batch(dbname, "CAP-MG-REPLAY-TEST-2")
    assert run_last_day(dbname).returncode == 1
    no_note = run_runner(dbname, "accept", "--log-id", str(log_id), "--note", " ", module="runner.guard")
    assert no_note.returncode != 0
    ok = run_runner(dbname, "accept", "--log-id", str(log_id), "--note", "phép thử: lô không có dòng", module="runner.guard")
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert run_last_day(dbname).returncode == 0
    assert last_run(dbname)[1] == "SUCCESS"
    assert query(dbname, f"select action, resolved_run_id from ctrl.guard_resolution where log_id = {log_id}") == [
        ("ACCEPTED", None)]
    assert query(dbname, "select count(*) from ctrl.v_guard_open") == [(0,)]
