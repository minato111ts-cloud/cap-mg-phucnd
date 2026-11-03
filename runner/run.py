"""
Runner CAP-MG: mô phỏng lịch chạy theo ngày của Finova (đề bài mục 2.1, 2.3.1, E.5).

Với từng ngày giao dịch D (ref_calendar.csv):
  1. cutoff(D) = 00:00 ngày D+1 giờ Việt Nam; loader nạp mọi lô chưa nạp có available_ts <= cutoff(D).
  2. Lấy cửa sổ (lo_ts, hi_ts] và max_log_id từ ctrl (bước 1 mục 2.3.1), ghi ctrl.batch_run RUNNING.
  3. T-GUARD (bước 2): có lô LOADED mang ingested_ts <= lo_ts mà log_id > max_log_id của lần SUCCESS trước
     thì ghi từng lô vào ctrl.guard_block, ghi BLOCKED_BY_GUARD và dừng, không chạy model nào.
     Người vận hành xử lý bằng full refresh hoặc python -m runner.guard (RV-10).
  4. dbt build staging (test GT-STG-*), ghi số dòng bị loại vào ctrl.reject_count (DEC-ELT-REJECT),
     rồi raw vault với --vars lo_ts, hi_ts, as_of_date.
  5. Xanh: SUCCESS (full refresh thì ghi đã xử lý cho các lô bị chặn mà nó phủ); đỏ: FAILED kèm error_msg,
     lo_ts của lần sau không đổi.
Business Vault, as-of và Gold cắm thêm vào STEPS khi có.

Chạy: uv run --env-file .env python -m runner.run [--from D] [--to D] [--full-refresh] [--skip-load]
Cần setup/ctrl.sql và setup/ctrl_runner.sql.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from loader.load import get_db_connection, load_manifest_batches

REPO_DIR = Path(__file__).resolve().parents[1]
DBT_DIR = REPO_DIR / "finova-dbt"
CALENDAR_CSV = DBT_DIR / "seeds" / "ref_calendar.csv"
VN_TZ = timezone(timedelta(hours=7))
# Kỳ chạy của đề (mục 2.1): lô nạp ban đầu 17/04, rồi từng ngày giao dịch tới 15/05/2026
DEFAULT_FROM = date(2026, 4, 17)
DEFAULT_TO = date(2026, 5, 15)

# Các bước dbt của một lần chạy, theo thứ tự E.5. Mỗi bước: (selector, có nhận --vars cửa sổ hay không)
STEPS: list[tuple[str, bool]] = [
    ("cap_mg_staging", False),
    ("cap_mg_raw", True),
]
# Sau bước này runner đếm dòng của các view __rejected trong cửa sổ (DEC-ELT-REJECT)
REJECT_COUNT_AFTER = "cap_mg_staging"
STAGING_SCHEMA = "staging"

# Mốc thời gian dạng ISO-8601 UTC, không phụ thuộc TimeZone/DateStyle của phiên; '-infinity' giữ nguyên chữ
# (psycopg2 đổi -infinity thành datetime.min, ghi lại sổ sẽ thành năm 0001)
ISO_TS = ("case when {c} = '-infinity' then '-infinity' "
          "else to_char({c} at time zone 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"+00:00\"') end")

# Bước 1 mục 2.3.1: cửa sổ cho lần chạy kế tiếp
SQL_WINDOW = f"""
with last_ok as (
  select hi_ts from ctrl.batch_run
  where status = 'SUCCESS' order by run_id desc limit 1
), cur as (
  select coalesce(max(log_id), 0) as max_log_id
  from ctrl.batch_log
), w as (
  select coalesce((select hi_ts from last_ok), '-infinity') as lo_ts,
         coalesce((select max(ingested_ts) from ctrl.batch_log l
                   where l.status = 'LOADED'
                     and l.log_id <= cur.max_log_id),
                  '-infinity') as hi_ts,
         cur.max_log_id
  from cur
)
select {ISO_TS.format(c='lo_ts')} as lo_ts, {ISO_TS.format(c='hi_ts')} as hi_ts, max_log_id
from w
"""

# Bước 2 mục 2.3.1: T-GUARD. Lô người vận hành đã ACCEPTED không chặn nữa (ctrl.guard_resolution)
SQL_GUARD = """
with prev as (
  select coalesce((select max_log_id from ctrl.batch_run
                   where status = 'SUCCESS'
                   order by run_id desc limit 1), 0) as prev_max_log_id
)
select l.log_id, l.batch_id, l.source_table, l.business_date, l.ingested_ts, l.rows_loaded, prev.prev_max_log_id
from ctrl.batch_log l
cross join prev
where l.status = 'LOADED'
  and l.ingested_ts <= %(lo_ts)s
  and l.log_id > prev.prev_max_log_id
  and not exists (select 1 from ctrl.guard_resolution r where r.log_id = l.log_id and r.action = 'ACCEPTED')
order by l.log_id
"""

SQL_GUARD_BLOCK = """
insert into ctrl.guard_block (run_id, log_id, batch_id, source_table, business_date, ingested_ts, rows_loaded,
                              prev_max_log_id, lo_ts)
values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

# Full refresh SUCCESS đã đưa mọi lô có log_id <= max_log_id vào vault: ghi đã xử lý cho các lô bị chặn đó
SQL_GUARD_RESOLVE = """
insert into ctrl.guard_resolution (log_id, action, resolved_run_id, resolved_by, note)
select o.log_id, 'FULL_REFRESH', %(run_id)s, 'runner', 'full refresh run_id ' || %(run_id)s
from ctrl.v_guard_open o
where o.log_id <= %(max_log_id)s
"""

SQL_REJECTED_VIEWS = """
select table_name from information_schema.views
where table_schema = %s and right(table_name, 10) = '__rejected'
order by table_name
"""

SQL_REJECT_COUNT = """
insert into ctrl.reject_count (run_id, batch_id, source_table, staging_view, reason_code, row_count)
select %(run_id)s, r.batch_id, l.source_table, %(view)s, r.reason_code, count(*)
from {view_rel} r
join ctrl.batch_log l on l.batch_id = r.batch_id and l.status = 'LOADED'
where r.ingested_ts > %(lo_ts)s::timestamptz and r.ingested_ts <= %(hi_ts)s::timestamptz
group by r.batch_id, l.source_table, r.reason_code
"""


def cutoff_of(d: date) -> datetime:
    """cutoff(D): hết ngày D, tức 00:00 ngày D+1 giờ Việt Nam (mục 2.1)."""
    nxt = d + timedelta(days=1)
    return datetime(nxt.year, nxt.month, nxt.day, tzinfo=VN_TZ)


def trading_days(d_from: date, d_to: date) -> list[date]:
    with CALENDAR_CSV.open(encoding="utf-8-sig", newline="") as fp:
        days = [date.fromisoformat(r["calendar_date"]) for r in csv.DictReader(fp) if r["is_trading_day"].strip() == "1"]
    return [d for d in sorted(days) if d_from <= d <= d_to]


def record_reject_counts(conn, run_id: int, lo_ts: str, hi_ts: str) -> None:
    """DEC-ELT-REJECT: ghi số dòng bị loại theo (batch_id, reason_code) của mọi view __rejected trong cửa sổ."""
    from psycopg2 import sql

    with conn.cursor() as cur:
        cur.execute("set role finova_dbt")
        cur.execute(SQL_REJECTED_VIEWS, (STAGING_SCHEMA,))
        for (view,) in cur.fetchall():
            stmt = sql.SQL(SQL_REJECT_COUNT).format(view_rel=sql.Identifier(STAGING_SCHEMA, view))
            cur.execute(stmt, {"run_id": run_id, "view": view, "lo_ts": lo_ts, "hi_ts": hi_ts})
    conn.commit()


def run_dbt(selector: str, dbt_vars: dict[str, str] | None, full_refresh: bool) -> tuple[bool, str]:
    from dbt.cli.main import dbtRunner

    # Unit test (mock {{ this }}) chạy lúc phát triển bằng dbt test --select test_type:unit, không chạy trong
    # lịch theo ngày: lần chạy đầu trên DB trống chưa có bảng incremental để dbt lấy kiểu cột.
    args = ["build", "--selector", selector, "--exclude-resource-type", "unit_test",
            "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR)]
    if dbt_vars is not None:
        args += ["--vars", json.dumps(dbt_vars)]
    if full_refresh:
        args.append("--full-refresh")
    res = dbtRunner().invoke(args)
    if res.success:
        return True, ""
    if res.exception is not None:
        return False, f"{selector}: {res.exception}"
    failed = [
        f"{r.node.name}: {r.status}"
        for r in (res.result or [])
        if str(r.status).lower() in ("error", "fail")
    ]
    return False, f"{selector}: " + "; ".join(failed[:10])


def run_day(d: date, full_refresh: bool = False, skip_load: bool = False) -> str:
    """Chạy pipeline cho ngày D; trả status ghi vào ctrl.batch_run."""
    cutoff = cutoff_of(d)
    if not skip_load:
        load_manifest_batches(cutoff_ts=cutoff)

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("select to_regclass('ctrl.guard_block') is not null and to_regclass('ctrl.reject_count') is not null")
            if not cur.fetchone()[0]:
                raise SystemExit("Thiếu bảng ctrl của runner: chạy setup/ctrl_runner.sql bằng postgres")
            cur.execute("set role finova_dbt")
            cur.execute(SQL_WINDOW)
            lo_ts, hi_ts, max_log_id = cur.fetchone()
            if full_refresh:
                lo_ts = "-infinity"
            cur.execute(
                """
                insert into ctrl.batch_run (as_of_date, cutoff_ts, lo_ts, hi_ts, max_log_id, full_refresh, status)
                values (%s, %s, %s, %s, %s, %s, 'RUNNING')
                returning run_id
                """,
                (d, cutoff, lo_ts, hi_ts, max_log_id, full_refresh),
            )
            run_id = cur.fetchone()[0]
        conn.commit()

        def finish(status: str, error_msg: str | None = None) -> str:
            with conn.cursor() as cur:
                cur.execute("set role finova_dbt")
                if status == "SUCCESS" and full_refresh:
                    cur.execute(SQL_GUARD_RESOLVE, {"run_id": run_id, "max_log_id": max_log_id})
                # finished_ts là giờ ghi sổ để vận hành tra cứu, không dùng lọc as-of hay incremental
                cur.execute(
                    "update ctrl.batch_run set status = %s, error_msg = %s, finished_ts = now() where run_id = %s",
                    (status, error_msg, run_id),
                )
            conn.commit()
            print(f"[runner] {d} run_id={run_id} lo={lo_ts} hi={hi_ts} -> {status}"
                  + (f" ({error_msg})" if error_msg else ""))
            return status

        with conn.cursor() as cur:
            cur.execute(SQL_GUARD, {"lo_ts": lo_ts})
            late = cur.fetchall()
            # ghi từng lô bị chặn; finish() commit cùng giao dịch với BLOCKED_BY_GUARD
            cur.executemany(SQL_GUARD_BLOCK, [(run_id, *row, lo_ts) for row in late])
        if late:
            detail = ", ".join(f"{b} (log_id {lid}, ingested_ts {ts.isoformat()})" for lid, b, _, _, ts, _, _ in late)
            return finish("BLOCKED_BY_GUARD", "T-GUARD: lô về sau lần chạy trước mà mang giờ cũ: " + detail
                          + ". Xem và xử lý: python -m runner.guard list")

        dbt_vars = {"lo_ts": lo_ts, "hi_ts": hi_ts, "as_of_date": d.isoformat()}
        for selector, takes_vars in STEPS:
            ok, err = run_dbt(selector, dbt_vars if takes_vars else None, full_refresh and takes_vars)
            if not ok:
                return finish("FAILED", err[:2000])
            if selector == REJECT_COUNT_AFTER:
                record_reject_counts(conn, run_id, lo_ts, hi_ts)
        return finish("SUCCESS")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Runner CAP-MG: chạy pipeline theo ngày giao dịch")
    parser.add_argument("--from", dest="d_from", type=date.fromisoformat, default=DEFAULT_FROM, help="Ngày D đầu (YYYY-MM-DD)")
    parser.add_argument("--to", dest="d_to", type=date.fromisoformat, default=DEFAULT_TO, help="Ngày D cuối (YYYY-MM-DD)")
    parser.add_argument("--full-refresh", action="store_true",
                        help="Một lần chạy cho ngày cuối với lo_ts = -infinity, dựng lại raw vault từ đầu (PT-FULL)")
    parser.add_argument("--skip-load", action="store_true", help="Không gọi loader (landing đã nạp sẵn)")
    args = parser.parse_args()

    days = trading_days(args.d_from, args.d_to)
    if not days:
        raise SystemExit("Không có ngày giao dịch nào trong khoảng đã chọn")
    if args.full_refresh:
        days = days[-1:]

    for d in days:
        status = run_day(d, full_refresh=args.full_refresh, skip_load=args.skip_load)
        if status != "SUCCESS":
            sys.exit(1)


if __name__ == "__main__":
    main()
