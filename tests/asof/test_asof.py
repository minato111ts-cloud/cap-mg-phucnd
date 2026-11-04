"""
Test tầng as-of (Bảng 24, 86, 87, 70): PT-ASOF-SINGLE, PT-NOFUTURE, TC-SLV-NOCUTOFF, TC-CAP-MG-FUTUREEFF.
TC-CAP-MG-BACKDATE cần kết quả của lần dựng đầu nên ở tests/raw (DB thử _ptfull).

View đọc cutoff từ GUC của phiên (finova.asof_cutoff, finova.asof_date); dbt test không có hook để đặt GUC trên
connection của test nên phần này dùng pytest. Chỉ đọc, chạy trên CAP_DBNAME khi runner đã SUCCESS ở đó.
    uv run --env-file .env pytest -q tests/asof
"""

from __future__ import annotations

import os
from datetime import date

import psycopg2
import pytest

from runner.run import ASOF_SCHEMA, ASOF_VIEWS, DEFAULT_FROM, cutoff_of, trading_days

# Grain của từng view (PT-ASOF-SINGLE: mỗi khóa một phiên bản; satellite theo ngày: mỗi khóa và ngày)
VIEW_KEYS = {
    "esat_reaflnk__flex": "reaflnk_hk",
    "link_reaflnk": "link_reaflnk_hk",
    "nhl_broker_event": "nhl_broker_event_hk",
    "sat_account_nav_daily__flex": "account_hk, business_date",
    "sat_broker_kpi__manual": "broker_hk",
    "sat_broker_profile__flex": "broker_hk",
    "sat_reaflnk__flex": "reaflnk_hk",
    "sat_regrp__flex": "regrp_hk",
}


def connect():
    conn = psycopg2.connect(
        host=os.environ.get("CAP_PGHOST", "127.0.0.1"),
        port=int(os.environ.get("CAP_PGPORT", "5436")),
        dbname=os.environ["CAP_DBNAME"],
        user=os.environ.get("CAP_PGUSER", "postgres"),
        password=os.environ["FINOVA_PG_PASSWORD"],
    )
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("set role finova_dbt")
    return conn


def set_day(cur, d: date) -> None:
    cur.execute("select set_config('finova.asof_date', %s, false), set_config('finova.asof_cutoff', %s, false)",
                (d.isoformat(), cutoff_of(d).isoformat()))


@pytest.fixture(scope="module")
def days() -> list[date]:
    """Ngày giao dịch đã chạy xong: từ DEFAULT_FROM tới as_of_date của lần SUCCESS gần nhất."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute("select table_name from information_schema.views where table_schema = %s", (ASOF_SCHEMA,))
        missing = set(ASOF_VIEWS) - {r[0] for r in cur.fetchall()}
        if missing:
            pytest.skip(f"Thiếu view as-of {sorted(missing)}: chạy runner hoặc dbt build --selector cap_mg_asof")
        cur.execute("select max(as_of_date) from ctrl.batch_run where status = 'SUCCESS'")
        last = cur.fetchone()[0]
    if last is None:
        pytest.skip("Runner chưa chạy SUCCESS")
    return trading_days(DEFAULT_FROM, last)


def test_view_keys_cover_all_views():
    assert sorted(VIEW_KEYS) == ASOF_VIEWS


@pytest.mark.parametrize("view", ASOF_VIEWS)
def test_tc_slv_nocutoff(view):
    """TC-SLV-NOCUTOFF: phiên chưa đặt cutoff (hoặc đặt rồi xóa thành chuỗi rỗng) đọc view thì báo lỗi."""
    for setup in (None, "select set_config('finova.asof_cutoff', '', false)"):
        with connect() as conn, conn.cursor() as cur:
            if setup:
                cur.execute(setup)
            with pytest.raises(psycopg2.Error, match="finova.asof_cutoff"):
                cur.execute(f"select count(*) from {ASOF_SCHEMA}.{view}")


def test_pt_asof_single(days):
    """PT-ASOF-SINGLE: tại mỗi ngày D, mỗi khóa (khóa và ngày với satellite theo ngày) đúng một dòng."""
    bad = []
    with connect() as conn, conn.cursor() as cur:
        for d in days:
            set_day(cur, d)
            for view, key in VIEW_KEYS.items():
                cur.execute(f"select count(*), count(distinct ({key})) from {ASOF_SCHEMA}.{view}")
                n, n_keys = cur.fetchone()
                if n != n_keys:
                    bad.append((d, view, n, n_keys))
    assert bad == []


def test_pt_nofuture(days):
    """PT-NOFUTURE: tại mỗi ngày D, không view nào trả dòng có ingested_ts sau cutoff(D)."""
    bad = []
    with connect() as conn, conn.cursor() as cur:
        for d in days:
            set_day(cur, d)
            for view in ASOF_VIEWS:
                cur.execute(f"select count(*) from {ASOF_SCHEMA}.{view} where ingested_ts > %s", (cutoff_of(d),))
                n = cur.fetchone()[0]
                if n:
                    bad.append((d, view, n))
    assert bad == []


def test_tc_cap_mg_futureeff(days):
    """TC-CAP-MG-FUTUREEFF (Bảng 70): phân công có FRDATE sau D không có hiệu lực tại D, dù hệ thống đã biết.
    Phép thử âm (theo đề): lọc theo ingested_ts thay vì FRDATE -> đỏ.
    Có ít nhất một ngày hệ thống đã biết phân công chưa tới hiệu lực, để test không xanh suông."""
    bad, known_future = [], 0
    with connect() as conn, conn.cursor() as cur:
        for d in days:
            set_day(cur, d)
            cur.execute(f"select count(*) from {ASOF_SCHEMA}.esat_reaflnk__flex"
                        " where not (fr_date <= %s and %s <= to_date)", (d, d))
            n = cur.fetchone()[0]
            if n:
                bad.append((d, n))
            cur.execute(f"select count(*) from {ASOF_SCHEMA}.sat_reaflnk__flex where fr_date > %s", (d,))
            known_future += cur.fetchone()[0]
    assert bad == []
    assert known_future > 0, "Dữ liệu không có phân công nào biết trước ngày hiệu lực: test không kiểm được gì"
