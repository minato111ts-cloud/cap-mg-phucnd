"""
Ghi lỗi vào bảng tập trung ctrl.error_log (setup/ctrl_log.sql), dùng chung cho loader, runner và bước dbt.

  - Kết nối riêng ở chế độ autocommit: dòng lỗi vẫn còn khi giao dịch nạp lô bị rollback.
  - Loader ghi bằng role finova_loader, runner và dbt bằng finova_dbt (ma trận quyền Bảng 13).
  - Che mật khẩu, DSN trước khi ghi (INV-S4).
  - Ghi lỗi không được làm hỏng luồng chính: không ghi được thì in ra stderr rồi đi tiếp.
"""

from __future__ import annotations

import os
import re
import sys

ROLE_OF = {"loader": "finova_loader", "runner": "finova_dbt", "dbt": "finova_dbt"}

SQL_INSERT = """
insert into ctrl.error_log (severity, component, step, object_name, run_id, batch_id, error_code, message)
values (%s, %s, %s, %s, %s, %s, %s, %s)
"""


def redact(text: str) -> str:
    """Che mật khẩu: giá trị của biến FINOVA_PG_PASSWORD, giá trị đi sau khóa password, và phần mật khẩu trong DSN postgres."""
    password = os.environ.get("FINOVA_PG_PASSWORD")
    if password:
        text = text.replace(password, "***")
    text = re.sub(r"(password\s*[=:]\s*)\S+", r"\1***", text, flags=re.IGNORECASE)
    return re.sub(r"(postgres(?:ql)?://[^:/@\s]+:)[^@\s]+@", r"\1***@", text)


def log_error(
    component: str,
    step: str,
    error_code: str,
    message: str,
    *,
    severity: str = "ERROR",
    object_name: str | None = None,
    run_id: int | None = None,
    batch_id: str | None = None,
) -> None:
    """Ghi một dòng vào ctrl.error_log: lỗi gì (error_code, message), ở đâu (component, step, object_name)."""
    from loader.load import get_db_connection  # import muộn: loader.load cũng import module này

    try:
        conn = get_db_connection(role=ROLE_OF[component], autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute(SQL_INSERT, (severity, component, step, object_name, run_id, batch_id,
                                         error_code, redact(message)))
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - lỗi ghi sổ không được che lỗi gốc
        print(f"[error_log] không ghi được ctrl.error_log ({exc.__class__.__name__}: {redact(str(exc))}); "
              f"lỗi gốc: {component}/{step}/{error_code}: {redact(message)}", file=sys.stderr)
