"""
Quy tắc LOAI của staging: dòng lỗi phải nằm ở view __rejected và không lọt vào view hợp lệ.

GT-STG-RECON chỉ cân tổng nên vẫn xanh khi dòng lỗi lọt sang view hợp lệ; các test này bắt trường hợp đó, cho DQ-NGAY-SAI,
DQ-MA-LA, DQ-KHOA-NULL. Chạy sau `dbt build --selector cap_mg_staging`, chỉ đọc.
    uv run --env-file .env pytest -q tests/staging
Phép thử âm: bỏ nhánh `when` của reason_code tương ứng ở macro staging, dbt build lại -> test đỏ.
"""

from __future__ import annotations

import os

import psycopg2
import pytest

pytestmark = pytest.mark.skipif(
    not (os.environ.get("CAP_DBNAME") and os.environ.get("FINOVA_PG_PASSWORD")),
    reason="Cần CAP_DBNAME, FINOVA_PG_PASSWORD và staging đã build",
)


@pytest.fixture(scope="module")
def cur():
    conn = psycopg2.connect(
        host=os.environ.get("CAP_PGHOST", "127.0.0.1"),
        port=int(os.environ.get("CAP_PGPORT", "5436")),
        dbname=os.environ["CAP_DBNAME"],
        user=os.environ.get("CAP_PGUSER", "postgres"),
        password=os.environ["FINOVA_PG_PASSWORD"],
    )
    conn.autocommit = True
    with conn.cursor() as c:
        c.execute("set role finova_dbt")
        c.execute("select to_regclass('staging.stg_flex__reaflnk')")
        if c.fetchone()[0] is None:
            pytest.skip("Chưa có view staging: chạy dbt build --selector cap_mg_staging")
        yield c
    conn.close()


def scalar(cur, sql: str) -> int:
    cur.execute(sql)
    return cur.fetchone()[0]


def test_dq_ngay_sai_stays_out_of_valid_view(cur):
    """DQ-NGAY-SAI: phân công có TODATE trước FRDATE chỉ ở __rejected."""
    assert scalar(cur, "select count(*) from staging.stg_flex__reaflnk where to_date < fr_date") == 0
    assert scalar(cur, "select count(*) from staging.stg_flex__reaflnk__rejected "
                       "where reason_code = 'INVALID_DATE_RANGE'") == 10


def test_dq_ma_la_stays_out_of_valid_view(cur):
    """DQ-MA-LA: event_type ngoài danh mục chỉ ở __rejected."""
    assert scalar(cur, """
        select count(*) from staging.stg_finova_app__events as e
        where not exists (select 1 from staging.ref_event_type as r where r.event_type = e.event_type)
    """) == 0
    assert scalar(cur, "select count(*) from staging.stg_finova_app__events__rejected "
                       "where reason_code = 'ALLCODE_UNKNOWN'") == 3


def test_dq_khoa_null_stays_out_of_valid_view(cur):
    """DQ-KHOA-NULL: sự kiện không có broker_id chỉ ở __rejected."""
    assert scalar(cur, "select count(*) from staging.stg_finova_app__events where broker_id is null") == 0
    assert scalar(cur, "select count(*) from staging.stg_finova_app__events__rejected "
                       "where reason_code = 'KEY_NULL'") == 4
