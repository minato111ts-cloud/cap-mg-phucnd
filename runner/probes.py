"""
Đáp án câu hỏi kiểm CAP-MG (Bảng 74) vào evidence/probes.csv (mục 2.7): probe_id, as_of, value, query, note.

Mỗi câu hỏi một file SQL thuần trong evidence/probes/ (tên file = mã câu hỏi), trả cột as_of, value cho từng mốc as-of.
Trainer chạy lại đúng file đó trên database, nên số không chép tay. Chạy bằng role finova_dbt (chủ bảng Gold, không bị
RLS lọc), sau khi runner đã dựng Gold tới ngày cần hỏi.

Chạy: uv run --env-file .env python -m runner.probes
"""

from __future__ import annotations

import csv
from pathlib import Path

from loader.load import get_db_connection

REPO_DIR = Path(__file__).resolve().parents[1]
PROBE_DIR = REPO_DIR / "evidence" / "probes"
OUT_CSV = REPO_DIR / "evidence" / "probes.csv"


def probe_id(path: Path) -> str:
    return path.stem.upper().replace("_", "-")


def note_of(sql: str) -> str:
    """Dòng comment đầu của file: câu hỏi của đề."""
    first = next((line for line in sql.splitlines() if line.startswith("--")), "")
    return first.removeprefix("--").strip()


def main() -> None:
    rows = []
    conn = get_db_connection(role="finova_dbt", autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("set timezone = 'Asia/Ho_Chi_Minh'")
            for path in sorted(PROBE_DIR.glob("*.sql")):
                sql = path.read_text(encoding="utf-8")
                cur.execute(sql)
                result = cur.fetchall()
                if not result:
                    rows.append([probe_id(path), "", "", path.relative_to(REPO_DIR).as_posix(), "KHÔNG CÓ DÒNG: " + note_of(sql)])
                for as_of, value in result:
                    rows.append([probe_id(path), as_of.isoformat(), value, path.relative_to(REPO_DIR).as_posix(), note_of(sql)])
    finally:
        conn.close()

    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["probe_id", "as_of", "value", "query", "note"])
        w.writerows(rows)
    for r in rows:
        print(" | ".join(r[:3]))


if __name__ == "__main__":
    main()
