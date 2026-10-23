"""SQL 守卫单测（§10.1）：覆盖放行与拦截两类共 30 例。"""

from __future__ import annotations

import pytest

from app.errors import AppError, ErrorCode
from app.services import sql_guard


def _rejected(sql: str) -> AppError:
    with pytest.raises(AppError) as info:
        sql_guard.validate_sql(sql)
    assert info.value.code == ErrorCode.SQL_REJECTED.value
    assert info.value.details.get("hint"), "拒绝原因必须带修复建议"
    return info.value


# ---------------------------------------------------------------- 放行
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM data",
        "SELECT channel, SUM(revenue) AS revenue FROM data GROUP BY channel",
        "SELECT * FROM data WHERE revenue > 100 ORDER BY revenue DESC LIMIT 10",
        "WITH monthly AS (SELECT channel, SUM(revenue) r FROM data GROUP BY channel) SELECT * FROM monthly",
        "SELECT channel FROM data UNION SELECT channel FROM data",
        "SELECT * FROM main.data",
        'SELECT * FROM "data"',
        "SELECT COUNT(DISTINCT order_id) FROM data",
        "SELECT ROW_NUMBER() OVER (PARTITION BY channel ORDER BY revenue DESC) rn FROM data",
        "SELECT 1",
        "SELECT * FROM data d JOIN (SELECT * FROM data) x ON d.order_id = x.order_id",
        "SELECT channel, SUM(revenue) FROM data WHERE channel IN ('DTC','Outlet') GROUP BY 1 HAVING SUM(revenue) > 0",
    ],
)
def test_allows_readonly_select(sql: str) -> None:
    assert sql_guard.validate_sql(sql) == sql


def test_comment_only_tail_is_single_statement() -> None:
    # "SELECT 1; --" 解析后只有一条语句，注释不构成第二条语句
    assert sql_guard.validate_sql("SELECT 1; --").startswith("SELECT 1")


# ---------------------------------------------------------------- 拦截：写操作
@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO data VALUES (1)",
        "UPDATE data SET revenue = 0",
        "DELETE FROM data",
        "DROP TABLE data",
        "CREATE TABLE t AS SELECT * FROM data",
        "ALTER TABLE data ADD COLUMN x INT",
        "ATTACH 'other.db' AS other",
        "PRAGMA database_list",
        "COPY data TO 'out.csv'",
        "SET enable_external_access=true",
        "TRUNCATE TABLE data",
        "CALL pragma_version()",
    ],
)
def test_blocks_writes(sql: str) -> None:
    _rejected(sql)


# ---------------------------------------------------------------- 拦截：多语句与外部
def test_blocks_multiple_statements() -> None:
    error = _rejected("SELECT * FROM data; SELECT * FROM data")
    assert "单条" in error.message


def test_blocks_read_csv() -> None:
    error = _rejected("SELECT * FROM read_csv('/etc/passwd')")
    assert "read_csv" in error.message


def test_blocks_other_table_with_name_in_message() -> None:
    error = _rejected("SELECT * FROM other_table")
    assert "other_table" in error.message


def test_blocks_subquery_from_external_table() -> None:
    error = _rejected("SELECT * FROM (SELECT * FROM secret_table) t")
    assert "secret_table" in error.message


def test_blocks_information_schema() -> None:
    error = _rejected("SELECT * FROM information_schema.tables")
    assert "information_schema" in str(error.details) or "information_schema" in error.message


def test_blocks_pg_catalog() -> None:
    _rejected("SELECT * FROM pg_catalog.pg_class")


def test_blocks_duckdb_internal() -> None:
    _rejected("SELECT * FROM duckdb_settings()")


def test_blocks_overlong_sql() -> None:
    error = _rejected("SELECT * FROM data WHERE " + "revenue > 1 AND " * 400 + "1=1")
    assert "长度" in error.message


def test_blocks_empty_sql() -> None:
    _rejected("   ")


def test_blocks_unparseable_sql() -> None:
    _rejected("SELEC * FROM data")


def test_rejects_glob_function() -> None:
    _rejected("SELECT * FROM glob('*')")


def test_rejects_parquet_scan() -> None:
    _rejected("SELECT * FROM parquet_scan('x.parquet')")


# ---------------------------------------------------------------- LIMIT 包装
def test_wrap_adds_outer_limit() -> None:
    wrapped = sql_guard.wrap_with_limit("SELECT * FROM data", 10)
    assert wrapped.startswith("SELECT * FROM ( SELECT * FROM data ) AS _mm_sub LIMIT 11")


def test_wrap_keeps_inner_limit() -> None:
    wrapped = sql_guard.wrap_with_limit("SELECT * FROM data LIMIT 5;", 10)
    assert "LIMIT 5" in wrapped
    assert wrapped.endswith("LIMIT 11")
