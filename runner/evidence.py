"""
Bằng chứng chạy (D-BANGCHUNG, Bảng 25): run_results.json của lần chạy theo ngày, lần chạy lại và lần full refresh, số dòng
từng tầng của mỗi lần, và bảng so (PT-IDEMP: chạy lại = theo ngày; PT-FULL: full refresh = theo ngày).

Dựng database riêng <CAP_DBNAME>_evidence từ đầu (xóa nếu có), rồi:
  1. runner theo lịch 17/04 -> 14/05 (không ghi bằng chứng);
  2. lần chạy theo ngày 15/05        -> evidence/run_daily/
  3. chạy lại đúng ngày 15/05        -> evidence/run_rerun/
  4. full refresh tới 15/05          -> evidence/run_full_refresh/
  5. evidence/row_counts_compare.csv: mỗi bảng, view một dòng, số dòng và md5 của ba lần, cột khớp.
Mỗi thư mục có <as_of_date>_<selector>.json (run_results.json của lần gọi dbt đó) và row_counts.csv.

Chạy: uv run --env-file .env python -m runner.evidence     (khoảng 10 phút)
"""

from __future__ import annotations

import csv
import os
import shutil
import subprocess
import sys

import psycopg2

from runner.run import DEFAULT_TO, REPO_DIR, trading_days, DEFAULT_FROM

EVIDENCE = REPO_DIR / "evidence"
RUNS = ["run_daily", "run_rerun", "run_full_refresh"]


def step(env: dict, *args: str) -> None:
    print("[evidence]", " ".join(args), flush=True)
    res = subprocess.run([sys.executable, "-m", *args], cwd=REPO_DIR, env=env)
    if res.returncode != 0:
        raise SystemExit(f"[evidence] lỗi ở bước: {' '.join(args)}")


def recreate_db(dbname: str) -> None:
    assert dbname.endswith("_evidence"), "Chỉ xóa và dựng lại database có hậu tố _evidence"
    conn = psycopg2.connect(host=os.environ.get("CAP_PGHOST", "127.0.0.1"), port=int(os.environ.get("CAP_PGPORT", "5436")),
                            dbname="postgres", user=os.environ.get("CAP_PGUSER", "postgres"),
                            password=os.environ["FINOVA_PG_PASSWORD"])
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f'drop database if exists "{dbname}" with (force)')
    conn.close()


def read_counts(run: str) -> dict[tuple[str, str], tuple[str, str]]:
    with (EVIDENCE / run / "row_counts.csv").open(encoding="utf-8", newline="") as f:
        return {(r["schema"], r["table"]): (r["rows"], r["md5"]) for r in csv.DictReader(f)}


def main() -> None:
    dbname = os.environ["CAP_DBNAME"] + "_evidence"
    env = dict(os.environ, CAP_DBNAME=dbname)
    last = DEFAULT_TO
    prev = trading_days(DEFAULT_FROM, last)[-2]

    recreate_db(dbname)
    for run in RUNS:
        shutil.rmtree(EVIDENCE / run, ignore_errors=True)
    step(env, "runner.init_db")
    step(env, "runner.run", "--to", prev.isoformat())
    day = ["--from", last.isoformat(), "--to", last.isoformat()]
    step(env, "runner.run", *day, "--evidence-dir", str(EVIDENCE / "run_daily"))
    step(env, "runner.run", *day, "--skip-load", "--evidence-dir", str(EVIDENCE / "run_rerun"))
    step(env, "runner.run", "--full-refresh", "--skip-load", "--to", last.isoformat(),
         "--evidence-dir", str(EVIDENCE / "run_full_refresh"))

    counts = {run: read_counts(run) for run in RUNS}
    keys = sorted(set().union(*[set(c) for c in counts.values()]),
                  key=lambda k: (["landing", "staging", "atomic", "asof", "mart"].index(k[0]), k[1]))
    mismatches = 0
    with (EVIDENCE / "row_counts_compare.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["schema", "table"] + [f"{r}_rows" for r in RUNS] + ["rerun_equals_daily", "full_refresh_equals_daily"])
        for k in keys:
            vals = [counts[r].get(k, ("", "")) for r in RUNS]
            same_rerun = vals[1] == vals[0]
            same_full = vals[2] == vals[0]
            mismatches += (not same_rerun) + (not same_full)
            w.writerow([*k, *[v[0] for v in vals], same_rerun, same_full])
    print(f"[evidence] {len(keys)} bảng, view; lệch: {mismatches}. Kết quả ở {EVIDENCE.relative_to(REPO_DIR)}/")
    if mismatches:
        sys.exit(1)


if __name__ == "__main__":
    main()
