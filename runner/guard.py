"""
Xử lý lô bị T-GUARD chặn (RV-10). Lô bị chặn nằm ở ctrl.guard_block; lô chưa xử lý ở ctrl.v_guard_open.

  list    Liệt kê lô chưa xử lý và lệnh xử lý gợi ý.
  accept  Cho chạy tiếp mà không đưa lô vào vault (ghi ctrl.guard_resolution ACCEPTED, bắt buộc --note).
          Lô vẫn ở landing; nó vào vault ở lần full refresh kế tiếp, với ingested_ts cũ của nó.

Cách xử lý mặc định là full refresh: python -m runner.run --full-refresh --skip-load --to <ngày D bị chặn>.
Lần full refresh SUCCESS tự ghi FULL_REFRESH cho mọi lô bị chặn mà nó phủ (runner/run.py).

Chạy: uv run --env-file .env python -m runner.guard list
      uv run --env-file .env python -m runner.guard accept --log-id 123 --note "lý do"
"""

from __future__ import annotations

import argparse
import getpass
import sys

from loader.load import get_db_connection

SQL_OPEN = """
select log_id, batch_id, source_table, business_date, ingested_ts, rows_loaded,
       first_lo_ts, blocked_runs, last_run_id, last_as_of_date
from ctrl.v_guard_open
order by log_id
"""


def list_open() -> int:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("set timezone = 'Asia/Ho_Chi_Minh'")
            cur.execute(SQL_OPEN)
            rows = cur.fetchall()
    finally:
        conn.close()
    if not rows:
        print("Không có lô nào đang bị T-GUARD chặn.")
        return 0
    print(f"{len(rows)} lô đang bị T-GUARD chặn:")
    for log_id, batch_id, table, bdate, ing_ts, n_rows, lo_ts, runs, last_run, last_d in rows:
        print(f"  log_id {log_id}: {batch_id} ({table}, ngày nghiệp vụ {bdate}, {n_rows} dòng)")
        print(f"    ingested_ts {ing_ts.isoformat()} <= lo_ts {lo_ts.isoformat()}; chặn {runs} lần, lần cuối run_id {last_run}")
    last_d = max(r[9] for r in rows)
    print("Cách xử lý:")
    print(f"  1. Đưa lô vào vault (mặc định): python -m runner.run --full-refresh --skip-load --to {last_d}")
    print("     rồi chạy tiếp theo lịch từ ngày sau đó.")
    print('  2. Chạy tiếp, chưa đưa lô vào vault: python -m runner.guard accept --log-id <log_id> --note "<lý do>"')
    return 0


def accept(log_id: int, note: str) -> int:
    if not note.strip():
        raise SystemExit("--note bắt buộc: ghi lý do cho chạy tiếp mà không đưa lô vào vault")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("select batch_id from ctrl.v_guard_open where log_id = %s", (log_id,))
            row = cur.fetchone()
            if row is None:
                raise SystemExit(f"log_id {log_id} không có trong ctrl.v_guard_open (chưa bị chặn hoặc đã xử lý)")
            cur.execute("set role finova_dbt")
            cur.execute(
                "insert into ctrl.guard_resolution (log_id, action, resolved_by, note) values (%s, 'ACCEPTED', %s, %s)",
                (log_id, getpass.getuser(), note.strip()),
            )
        conn.commit()
    finally:
        conn.close()
    print(f"Đã ghi ACCEPTED cho log_id {log_id} ({row[0]}). Lần chạy sau T-GUARD bỏ qua lô này;"
          " lô vào vault ở lần full refresh kế tiếp.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Xử lý lô bị T-GUARD chặn")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="Liệt kê lô đang bị chặn")
    p_acc = sub.add_parser("accept", help="Cho chạy tiếp mà không đưa lô vào vault")
    p_acc.add_argument("--log-id", type=int, required=True)
    p_acc.add_argument("--note", required=True)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(list_open() if args.cmd == "list" else accept(args.log_id, args.note))


if __name__ == "__main__":
    main()
