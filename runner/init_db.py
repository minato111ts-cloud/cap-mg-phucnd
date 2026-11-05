"""
Dựng database của capstone (D-RUNBOOK, mục 2.2): tạo CAP_DBNAME nếu chưa có, rồi chạy các file setup theo thứ tự
bằng user CAP_PGUSER (mặc định postgres). Các file setup chạy lại nhiều lần không lỗi, nên lệnh này cũng vậy.

Bỏ các dòng lệnh riêng của psql (\\encoding, \\set): psycopg2 không hiểu, và lỗi SQL đã dừng lệnh như ON_ERROR_STOP.

Chạy: uv run --env-file .env python -m runner.init_db
"""

from __future__ import annotations

import os
from pathlib import Path

from psycopg2 import sql

from loader.load import pg_connect

REPO_DIR = Path(__file__).resolve().parents[1]
SETUP_FILES = ["bootstrap.sql", "ctrl.sql", "ctrl_runner.sql", "ctrl_log.sql"]


def setup_sql(path: Path) -> str:
    return "\n".join(line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("\\"))


def main() -> None:
    dbname = os.environ["CAP_DBNAME"]
    admin = pg_connect("postgres")
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute("select 1 from pg_database where datname = %s", (dbname,))
        if cur.fetchone() is None:
            cur.execute(sql.SQL("create database {}").format(sql.Identifier(dbname)))
            print(f"[init_db] tạo database {dbname}")
    admin.close()

    conn = pg_connect(dbname)
    try:
        for name in SETUP_FILES:
            with conn.cursor() as cur:
                cur.execute(setup_sql(REPO_DIR / "setup" / name))
            conn.commit()
            print(f"[init_db] {dbname}: setup/{name}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
