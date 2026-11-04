"""
TC-CAP-E2E (Bảng 24, tầng đầu cuối): lần theo thực thể từ dòng landing tới chỉ số Gold, qua đủ các tầng.

Mỗi ngày D đã dựng Gold, với mọi tiểu khoản có phân công ở mart.dim_account_care_daily:
  phân công: Gold -> bridge_account_broker (BV) -> asof.esat_reaflnk__flex (GUC của D) -> sat_reaflnk__flex (raw, cùng
             ingested_ts, hash_diff) -> stg_flex__reaflnk (cùng khóa, ingested_ts, hashdiff) -> landing.flex_reaflnk
             (cùng batch_id, source_row_no; AUTOID, REACCTNO, AFACCTNO khớp);
  NAV:       pit_account_daily -> sat_account_nav_daily__flex (raw) -> stg_flex__nav -> landing.ref_nav, rồi
             Σ NAV lần được theo môi giới bằng book_nav của met_broker_daily.
Mỗi mắt xích đứt là một dòng lỗi kèm tầng. Không nêu tên thực thể nào: mọi tiểu khoản, mọi ngày.
Chỉ đọc, chạy trên CAP_DBNAME khi runner đã dựng Gold.
    uv run --env-file .env pytest -q tests/e2e
"""

from __future__ import annotations

import os

import psycopg2
import pytest

from runner.run import cutoff_of

SQL_TRACE = """
with gold as (
    select account_id, account_hk, broker_hk, broker_id, broker_key, reaflnk_autoid, fr_date, to_date
    from mart.dim_account_care_daily
    where as_of_date = %(d)s and is_assigned
),
bv as (
    select account_hk, broker_hk, reaflnk_hk from atomic.bridge_account_broker where as_of_date = %(d)s
),
asof_row as (
    select reaflnk_hk, broker_hk, account_hk, autoid, fr_date, to_date, ingested_ts, hash_diff from asof.esat_reaflnk__flex
),
chain as (
    select
        g.account_id,
        b.reaflnk_hk is not null as ok_bv,
        a.reaflnk_hk is not null as ok_asof,
        r.reaflnk_hk is not null as ok_raw,
        s.reaflnk_hk is not null as ok_stg,
        l.batch_id is not null as ok_landing
    from gold as g
    left join bv as b on b.account_hk = g.account_hk and b.broker_hk = g.broker_hk
    left join asof_row as a
        on a.reaflnk_hk = b.reaflnk_hk and a.broker_hk = g.broker_hk and a.account_hk = g.account_hk
       and a.autoid = g.reaflnk_autoid and a.fr_date = g.fr_date and a.to_date = g.to_date
    left join atomic.sat_reaflnk__flex as r
        on r.reaflnk_hk = a.reaflnk_hk and r.ingested_ts = a.ingested_ts and r.hash_diff = a.hash_diff
    left join lateral (
        select st.reaflnk_hk, st.batch_id, st.source_row_no
        from staging.stg_flex__reaflnk as st
        where st.reaflnk_hk = r.reaflnk_hk and st.ingested_ts = r.ingested_ts and st.sat_reaflnk_hd = r.hash_diff
        limit 1
    ) as s on true
    left join landing.flex_reaflnk as l
        on l.batch_id = s.batch_id and l.source_row_no = s.source_row_no
       and btrim(l.autoid) = g.reaflnk_autoid and btrim(l.reacctno) = g.broker_id and btrim(l.afacctno) = g.account_id
)
select account_id,
       case when not ok_bv then 'GOLD->BV' when not ok_asof then 'BV->ASOF' when not ok_raw then 'ASOF->RAW'
            when not ok_stg then 'RAW->STAGING' else 'STAGING->LANDING' end as broken_at
from chain
where not (ok_bv and ok_asof and ok_raw and ok_stg and ok_landing)
"""

SQL_NAV = """
with gold as (
    select account_hk, broker_key from mart.dim_account_care_daily where as_of_date = %(d)s and broker_key is not null
),
traced as (
    select g.broker_key, g.account_hk, st.nav, l.batch_id is not null as ok_landing
    from gold as g
    join atomic.pit_account_daily as p on p.as_of_date = %(d)s and p.account_hk = g.account_hk
    join atomic.sat_account_nav_daily__flex as r
      on r.account_hk = p.account_hk and r.business_date = p.as_of_date and r.ingested_ts = p.sat_account_nav_ingested_ts
    join lateral (
        select s.nav, s.batch_id, s.source_row_no
        from staging.stg_flex__nav as s
        where s.account_hk = r.account_hk and s.tx_date = r.business_date and s.ingested_ts = r.ingested_ts
          and s.sat_account_nav_hd = r.hash_diff
        limit 1
    ) as st on true
    left join landing.ref_nav as l on l.batch_id = st.batch_id and l.source_row_no = st.source_row_no
),
per_broker as (
    select broker_key, coalesce(sum(nav), 0) as nav, count(*) filter (where not ok_landing) as n_no_landing
    from traced group by broker_key
)
select m.broker_key, m.book_nav, coalesce(t.nav, 0) as traced_nav, coalesce(t.n_no_landing, 0)
from mart.met_broker_daily as m
left join per_broker as t on t.broker_key = m.broker_key
where m.as_of_date = %(d)s
  and (m.book_nav is distinct from coalesce(t.nav, 0) or coalesce(t.n_no_landing, 0) > 0)
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


@pytest.fixture(scope="module")
def days() -> list:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("select to_regclass('mart.dim_account_care_daily') is not null")
        if not cur.fetchone()[0]:
            pytest.skip("Chưa có Gold: chạy runner")
        cur.execute("select distinct as_of_date from mart.dim_account_care_daily order by 1")
        out = [r[0] for r in cur.fetchall()]
    if not out:
        pytest.skip("Gold chưa có ngày nào")
    return out


def test_tc_cap_e2e_assignment_lineage(days):
    """Mọi tiểu khoản có phân công ở Gold, mọi ngày: lần được tới đúng dòng landing qua BV, as-of, raw, staging."""
    problems, traced = [], 0
    with connect() as conn, conn.cursor() as cur:
        for d in days:
            cur.execute("select set_config('finova.asof_date', %s, false), set_config('finova.asof_cutoff', %s, false)",
                        (d.isoformat(), cutoff_of(d).isoformat()))
            cur.execute(SQL_TRACE, {"d": d})
            problems += [f"{d} {acc}: đứt ở {where}" for acc, where in cur.fetchall()]
            cur.execute("select count(*) from mart.dim_account_care_daily where as_of_date = %s and is_assigned", (d,))
            traced += cur.fetchone()[0]
    assert not problems, "\n".join(problems[:20])
    assert traced > 0


def test_tc_cap_e2e_booknav_from_landing(days):
    """CAP-MG-BOOKNAV của mỗi môi giới, mỗi ngày = Σ NAV lần ngược từ PIT qua raw, staging tới dòng landing ref_nav."""
    problems = []
    with connect() as conn, conn.cursor() as cur:
        for d in days:
            cur.execute(SQL_NAV, {"d": d})
            problems += [f"{d} {bk}: book_nav {nav} != lần từ landing {t} (thiếu landing {n})" for bk, nav, t, n in cur.fetchall()]
    assert not problems, "\n".join(problems[:20])
