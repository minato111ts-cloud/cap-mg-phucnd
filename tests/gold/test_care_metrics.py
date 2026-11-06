"""
Test Gold cho các mã D-TEST chưa có test riêng: DQ-QUYEN, TH-NHAPTAY, TH-NGHIVIEC, DEC-CAP-MG-BROKERKEY.

- DQ-QUYEN: tử CAP-MG-COVER30 tính lại từ view as-of bằng Python, độc lập với SQL của met_broker_daily (Bảng 72).
- TH-NHAPTAY: phiên bản chỉ tiêu của ngày D suy từ sổ nạp; dòng bị loại không có chỉ tiêu.
- TH-NGHIVIEC, DEC-CAP-MG-GAP: cờ is_carer_inactive khớp work_status; 13 tiểu khoản của BRK017 chuyển đủ cho BRK018.
- DEC-CAP-MG-BROKERKEY: người mới mang mã BRK017 không nhận tương tác của người cũ.

Chỉ đọc, chạy trên CAP_DBNAME khi runner đã dựng Gold.
    uv run --env-file .env pytest -q tests/gold
Phép thử âm ghi ở docs/matran_test.md.
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import psycopg2
import pytest

VN = timezone(timedelta(hours=7))
COVER_DAYS = 30
SQL_ASSIGNMENT = """
select encode(l.broker_hk, 'hex'), encode(l.account_hk, 'hex'), s.fr_date, s.to_date
from asof.sat_reaflnk__flex as s
join asof.link_reaflnk as l on l.reaflnk_hk = s.reaflnk_hk
"""


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
    cutoff = datetime(d.year, d.month, d.day, tzinfo=VN) + timedelta(days=1)
    cur.execute("select set_config('finova.asof_date', %s, false), set_config('finova.asof_cutoff', %s, false)",
                (d.isoformat(), cutoff.isoformat()))


@pytest.fixture(scope="module")
def cur():
    conn = connect()
    with conn.cursor() as c:
        c.execute("select to_regclass('mart.met_broker_daily')")
        if c.fetchone()[0] is None:
            pytest.skip("Chưa có bảng Gold: chạy runner")
        yield c
    conn.close()


@pytest.fixture(scope="module")
def days(cur) -> list[date]:
    cur.execute("select distinct as_of_date from mart.met_broker_daily order by 1")
    result = [r[0] for r in cur.fetchall()]
    if not result:
        pytest.skip("Gold chưa có ngày nào")
    return result


def cover30_numerators(cur, d: date) -> dict:
    """Tử COVER30 của ngày D theo broker_key, tính lại từ view as-of theo Bảng 72."""
    set_day(cur, d)
    cur.execute(SQL_ASSIGNMENT)
    assigned = defaultdict(list)
    for broker_hk, account_hk, fr_date, to_date in cur.fetchall():
        assigned[broker_hk, account_hk].append((fr_date, to_date))

    cur.execute("""
        select c.broker_key, encode(c.broker_hk, 'hex'), encode(c.account_hk, 'hex'), o.join_date, o.leave_date
        from mart.dim_account_care_daily as c
        join mart.dim_broker_org_daily as o on o.as_of_date = c.as_of_date and o.broker_key = c.broker_key
        where c.as_of_date = %s
    """, (d,))
    care = cur.fetchall()

    cur.execute("""
        select encode(broker_hk, 'hex'), encode(account_hk, 'hex'), event_date
        from asof.nhl_broker_event
        where event_date between %s and %s
    """, (d - timedelta(days=COVER_DAYS - 1), d))
    events = defaultdict(list)
    for broker_hk, account_hk, event_date in cur.fetchall():
        events[broker_hk, account_hk].append(event_date)

    numerators = defaultdict(int)
    for broker_key, broker_hk, account_hk, join_date, leave_date in care:
        worked = [e for e in events[broker_hk, account_hk]
                  if (join_date is None or e >= join_date) and (leave_date is None or e <= leave_date)]
        numerators[broker_key] += any(fr <= e <= to for e in worked for fr, to in assigned[broker_hk, account_hk])
    return numerators


def test_dq_quyen_not_in_cover30(cur, days):
    """DQ-QUYEN: tương tác vào ngày chưa được giao tiểu khoản không vào tử CAP-MG-COVER30.

    Dữ liệu đề không có tương tác nào của môi giới với tiểu khoản đang chăm sóc mà rơi ngoài ngày được giao, nên phép
    thử âm phải chèn sự kiện giả (docs/matran_test.md).
    """
    mismatch = []
    for d in days:
        numerators = cover30_numerators(cur, d)
        cur.execute("select broker_key, cover30_num from mart.met_broker_daily where as_of_date = %s", (d,))
        mismatch += [(d, k, num, numerators[k]) for k, num in cur.fetchall() if num != numerators[k]]
    assert not mismatch, mismatch[:5]


def test_dq_quyen_events_have_no_assignment(cur):
    """Mọi sự kiện dq_mg_daily ghi EVENT_NOT_ASSIGNED đều không có phân công của chính môi giới vào ngày sự kiện."""
    cur.execute("select as_of_date, key_sample from mart.dq_mg_daily where reason_code = 'EVENT_NOT_ASSIGNED'")
    flagged = cur.fetchall()
    assert flagged, "Dữ liệu đề có DQ-QUYEN"
    for d, key_sample in flagged:
        set_day(cur, d)
        cur.execute(SQL_ASSIGNMENT)
        assigned = defaultdict(list)
        for broker_hk, account_hk, fr_date, to_date in cur.fetchall():
            assigned[broker_hk, account_hk].append((fr_date, to_date))
        cur.execute("""
            select event_id, encode(broker_hk, 'hex'), encode(account_hk, 'hex'), event_date
            from asof.nhl_broker_event where event_id = any(%s)
        """, (key_sample.split(";"),))
        rows = cur.fetchall()
        assert rows
        for event_id, broker_hk, account_hk, event_date in rows:
            assert not any(fr <= event_date <= to for fr, to in assigned[broker_hk, account_hk]), (d, event_id)


def test_th_nhaptay_kpi_version_by_cutoff(cur, days):
    """TH-NHAPTAY: ngày D dùng phiên bản chỉ tiêu mới nhất có ingested_ts <= cutoff(D), không dùng phiên bản sau."""
    cur.execute("""
        select batch_id, ingested_ts from ctrl.batch_log
        where source_table = 'manual_kpi' and status = 'LOADED' order by ingested_ts
    """)
    versions = cur.fetchall()
    assert len(versions) == 2, "Đề có hai phiên bản file chỉ tiêu"
    for d in days:
        cur.execute("select distinct cutoff_ts from mart.met_broker_daily where as_of_date = %s", (d,))
        cutoff = cur.fetchone()[0]
        known = [batch_id for batch_id, ingested_ts in versions if ingested_ts <= cutoff]
        cur.execute("select distinct kpi_batch_id from mart.met_broker_daily "
                    "where as_of_date = %s and kpi_batch_id is not null", (d,))
        assert {r[0] for r in cur.fetchall()} == set(known[-1:]), d


def test_th_nhaptay_v2_replaces_v1_target(cur, days):
    """TH-NHAPTAY: chỉ tiêu trong Gold bằng chỉ tiêu của đúng phiên bản; có môi giới đổi số giữa hai bản."""
    cur.execute("select batch_id, broker_id, target_calls from staging.stg_manual__kpi")
    target = {(b, k): v for b, k, v in cur.fetchall()}
    cur.execute("""
        select as_of_date, broker_id, kpi_batch_id, kpi_target_calls
        from mart.met_broker_daily where kpi_batch_id is not null
    """)
    rows = cur.fetchall()
    assert rows
    for d, broker_id, batch_id, calls in rows:
        assert calls == target[batch_id, broker_id], (d, broker_id)
    batches = sorted({b for b, _ in target})
    assert any(target[batches[0], k] != target[batches[1], k] for b, k in target if b == batches[0])


def test_th_nhaptay_rejected_rows_have_no_target(cur):
    """Dòng chưa duyệt, dòng lỗi công thức (DQ-CHUADUYET, DQ-CONGTHUC) không có chỉ tiêu ở mọi ngày."""
    cur.execute("select distinct broker_id from staging.stg_manual__kpi__rejected")
    rejected = [r[0] for r in cur.fetchall()]
    assert rejected
    cur.execute("select count(*) from mart.met_broker_daily where broker_id = any(%s) and kpi_target_calls is not null",
                (rejected,))
    assert cur.fetchone()[0] == 0


def test_th_nghiviec_flag_follows_work_status(cur):
    """DEC-CAP-MG-GAP: tiểu khoản gắn người không còn làm thì có cờ và care_basis; ngược lại không có."""
    cur.execute("""
        select c.as_of_date, c.account_id, c.is_carer_inactive, c.care_basis, o.work_status
        from mart.dim_account_care_daily as c
        left join mart.dim_broker_org_daily as o on o.as_of_date = c.as_of_date and o.broker_key = c.broker_key
        where c.is_assigned
    """)
    for d, account_id, inactive, care_basis, work_status in cur.fetchall():
        expected = work_status != "ACTIVE"
        assert inactive == expected, (d, account_id, work_status)
        assert ("DEC-CAP-MG-GAP" in care_basis) == expected, (d, account_id, care_basis)


def test_th_nghiviec_accounts_move_to_successor(cur):
    """TH-NGHIVIEC: BRK017 nghỉ; toàn bộ tiểu khoản của BRK017 ở ngày cuối trước khi nghỉ thuộc BRK018 từ 04/05."""
    cur.execute("select array_agg(account_id) from mart.dim_account_care_daily "
                "where as_of_date = '2026-04-29' and broker_id = 'BRK017'")
    accounts = cur.fetchone()[0]
    assert len(accounts) == 13
    cur.execute("select broker_id, count(*) from mart.dim_account_care_daily "
                "where as_of_date = '2026-05-04' and account_id = any(%s) group by 1", (accounts,))
    assert cur.fetchall() == [("BRK018", 13)]


def test_dec_brokerkey_new_holder_has_no_old_interactions(cur):
    """DEC-CAP-MG-BROKERKEY: người mang mã BRK017 từ 11/05 có 0 tiểu khoản, 0 tương tác; người cũ thì có."""
    cur.execute("""
        select broker_key, as_of_date, n_accounts, book_nav, interactions_30d
        from mart.met_broker_daily where broker_id = 'BRK017' order by as_of_date
    """)
    rows = cur.fetchall()
    new_holder = [r for r in rows if r[1] >= date(2026, 5, 11)]
    assert new_holder and all(r[0] == "BRK017:2026-05-11" for r in new_holder)
    assert all(r[2:] == (0, 0, 0) for r in new_holder), new_holder
    assert any(r[4] > 0 for r in rows if r[1] < date(2026, 5, 11)), "Người cũ phải có tương tác: test xanh suông"
