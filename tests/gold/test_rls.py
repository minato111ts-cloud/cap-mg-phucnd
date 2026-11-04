"""
TC-CAP-MG-RLS (Bảng 70, INV-SEM-RLSDB): mỗi vai trò trong org_roles.csv chỉ thấy tiểu khoản thuộc phạm vi của mình tại D,
do policy RLS của database lọc.

Phiên đọc dùng role finova_app (setup/bootstrap.sql) và đặt finova.viewer_id như ứng dụng. Tập "phải thấy" tính độc lập
với Gold, từ Business Vault và raw vault: tiểu khoản trong bridge_account_broker của D, môi giới của nó (hồ sơ qua con
trỏ PIT) có mã bằng phạm vi, hoặc đơn vị của môi giới có phạm vi là cấp trên trong bridge_regrp_ancestor của D.
Chỉ đọc, chạy trên CAP_DBNAME khi runner đã dựng Gold.
    uv run --env-file .env pytest -q tests/gold
Phép thử âm (theo đề): cho BRK003 xem tiểu khoản của BRK009 -> đỏ.
"""

from __future__ import annotations

import os
from datetime import date

import psycopg2
import pytest

RLS_TABLES = ["dim_account_care_daily", "sec_visibility_daily", "dim_broker_org_daily", "met_broker_daily"]

SQL_EXPECTED = """
with prof as (
    select p.broker_hk, s.broker_id, s.grpid
    from atomic.pit_broker_daily as p
    join atomic.sat_broker_profile__flex as s
      on s.broker_hk = p.broker_hk and s.ingested_ts = p.sat_broker_profile_ingested_ts
    where p.as_of_date = %(d)s
),
unit as (select distinct regrp_hk, grpid from atomic.sat_regrp__flex),
anc as (
    select u.grpid, ua.grpid as ancestor_grpid
    from atomic.bridge_regrp_ancestor as a
    join unit as u on u.regrp_hk = a.regrp_hk
    join unit as ua on ua.regrp_hk = a.ancestor_regrp_hk
    where a.as_of_date = %(d)s
),
in_scope as (
    select pr.broker_hk, pr.broker_id
    from prof as pr
    where pr.broker_id = %(scope)s
       or exists (select 1 from anc where anc.grpid = pr.grpid and anc.ancestor_grpid = %(scope)s)
),
account_id as (
    select distinct l.account_hk, s.afacctno
    from atomic.link_reaflnk as l
    join atomic.sat_reaflnk__flex as s on s.reaflnk_hk = l.reaflnk_hk
)
select 'account' as kind, ai.afacctno
from atomic.bridge_account_broker as b
join in_scope as i on i.broker_hk = b.broker_hk
join account_id as ai on ai.account_hk = b.account_hk
where b.as_of_date = %(d)s
union all
select 'broker', broker_id from in_scope
"""


def connect(role: str):
    conn = psycopg2.connect(
        host=os.environ.get("CAP_PGHOST", "127.0.0.1"),
        port=int(os.environ.get("CAP_PGPORT", "5436")),
        dbname=os.environ["CAP_DBNAME"],
        user=os.environ.get("CAP_PGUSER", "postgres"),
        password=os.environ["FINOVA_PG_PASSWORD"],
    )
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f"set role {role}")
    return conn


@pytest.fixture(scope="module")
def setup() -> dict:
    with connect("finova_dbt") as conn, conn.cursor() as cur:
        cur.execute("select count(*) from information_schema.tables where table_schema = 'mart' and table_name = any(%s)",
                    (RLS_TABLES,))
        if cur.fetchone()[0] < len(RLS_TABLES):
            pytest.skip("Chưa có bảng Gold: chạy runner")
        cur.execute("select distinct as_of_date from mart.dim_account_care_daily order by 1")
        days = [r[0] for r in cur.fetchall()]
        cur.execute("select viewer_id, scope from staging.ref_org_roles order by viewer_id")
        viewers = cur.fetchall()
        expected = {}
        for d in days:
            for viewer, scope in viewers:
                cur.execute(SQL_EXPECTED, {"d": d, "scope": scope})
                rows = cur.fetchall()
                expected[(d, viewer)] = ({v for k, v in rows if k == "account"}, {v for k, v in rows if k == "broker"})
    if not days:
        pytest.skip("Gold chưa có ngày nào")
    return {"days": days, "viewers": [v for v, _ in viewers], "expected": expected}


def visible(viewer: str | None, d: date) -> dict[str, set]:
    """Những gì phiên finova_app thấy ở ngày D với người xem cho trước (None: không đặt)."""
    with connect("finova_app") as conn, conn.cursor() as cur:
        if viewer is not None:
            cur.execute("select set_config('finova.viewer_id', %s, false)", (viewer,))
        out = {}
        cur.execute("select account_id from mart.dim_account_care_daily where as_of_date = %s", (d,))
        out["care"] = {r[0] for r in cur.fetchall()}
        cur.execute("select viewer_id, account_id from mart.sec_visibility_daily where as_of_date = %s", (d,))
        sec = cur.fetchall()
        out["sec_viewers"] = {r[0] for r in sec}
        out["sec_accounts"] = {r[1] for r in sec}
        cur.execute("select broker_id from mart.dim_broker_org_daily where as_of_date = %s", (d,))
        out["dim_broker"] = {r[0] for r in cur.fetchall()}
        cur.execute("select broker_id from mart.met_broker_daily where as_of_date = %s", (d,))
        out["met"] = {r[0] for r in cur.fetchall()}
    return out


def test_tc_cap_mg_rls(setup):
    """Mỗi người xem, mỗi ngày: tiểu khoản thấy ở dim_account_care_daily, sec_visibility_daily đúng bằng tập phải thấy;
    sec_visibility_daily chỉ có dòng của chính mình; môi giới thấy ở dim_broker_org_daily, met_broker_daily đúng phạm vi."""
    problems = []
    for d in setup["days"]:
        for viewer in setup["viewers"]:
            accounts, brokers = setup["expected"][(d, viewer)]
            got = visible(viewer, d)
            if got["care"] != accounts:
                problems.append(f"{d} {viewer} dim_account_care_daily: thừa {sorted(got['care'] - accounts)[:5]}, "
                                f"thiếu {sorted(accounts - got['care'])[:5]}")
            if got["sec_accounts"] != accounts or got["sec_viewers"] - {viewer}:
                problems.append(f"{d} {viewer} sec_visibility_daily: viewer {sorted(got['sec_viewers'])}, "
                                f"thừa {sorted(got['sec_accounts'] - accounts)[:5]}")
            for t in ("dim_broker", "met"):
                if got[t] != brokers:
                    problems.append(f"{d} {viewer} {t}: thừa {sorted(got[t] - brokers)}, thiếu {sorted(brokers - got[t])}")
    assert not problems, "\n".join(problems[:20])


def test_tc_cap_mg_rls_not_vacuous(setup):
    """Mỗi người xem có tiểu khoản phải thấy ở ít nhất một ngày, và hai người xem khác nhau không cùng một tập."""
    for viewer in setup["viewers"]:
        assert any(setup["expected"][(d, viewer)][0] for d in setup["days"]), viewer
    d = setup["days"][-1]
    sets = [frozenset(setup["expected"][(d, v)][0]) for v in setup["viewers"]]
    assert len(set(sets)) > 1


@pytest.mark.parametrize("viewer", [None, "", "KHONG-CO-TRONG-ORG-ROLES"])
def test_rls_no_scope_sees_nothing(setup, viewer):
    """Phiên không đặt người xem, đặt rỗng, hoặc người xem không có trong org_roles: không thấy dòng nào."""
    got = visible(viewer, setup["days"][-1])
    assert all(not v for v in got.values()), {k: len(v) for k, v in got.items()}
