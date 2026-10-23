"""只读 SQL 守卫（§5.2(3)）：sqlglot AST 逐条规则校验，失败抛 SQL_REJECTED。

为什么不用正则：注释注入、CTE、UNION、函数调用都可以绕过字符串匹配；
唯一可靠的做法是解析成 AST 后按节点类型与表名白名单判定。
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from ..errors import AppError, ErrorCode

MAX_SQL_CHARS = 4000
ALLOWED_TABLE = "data"
ALLOWED_SCHEMAS = frozenset({"", "main"})

FORBIDDEN_FUNCTIONS = frozenset(
    {
        "read_csv",
        "read_csv_auto",
        "read_parquet",
        "read_json",
        "read_json_auto",
        "parquet_scan",
        "csv_scan",
        "json_scan",
        "glob",
        "sniff_csv",
        "sqlite_scan",
        "postgres_scan",
        "mysql_scan",
        "delta_scan",
        "iceberg_scan",
        "httpfs",
        "install",
        "load",
        "copy",
        "export_database",
    }
)

FORBIDDEN_NODE_NAMES = (
    "Insert",
    "Update",
    "Delete",
    "Create",
    "Drop",
    "Alter",
    "Attach",
    "Detach",
    "Copy",
    "Pragma",
    "Set",
    "Command",
    "Export",
    "Load",
    "Install",
    "Use",
    "Grant",
    "TruncateTable",
    "Transaction",
    "Commit",
    "Rollback",
)


def _forbidden_nodes() -> tuple[type, ...]:
    nodes: list[type] = []
    for name in FORBIDDEN_NODE_NAMES:
        node = getattr(exp, name, None)
        if isinstance(node, type) and issubclass(node, exp.Expression):
            nodes.append(node)
    return tuple(nodes)


FORBIDDEN_NODES = _forbidden_nodes()


def _reject(reason: str, hint: str) -> AppError:
    return AppError(
        ErrorCode.SQL_REJECTED,
        f"出于安全限制，只允许对 data 视图的只读查询：{reason}",
        details={"reason": reason},
        hint=hint,
    )


def _normalize_identifier(name: str) -> str:
    return name.strip().strip('"`[]').lower()


def _function_name(node: exp.Expression) -> str:
    """统一取函数名：匿名函数取原文名字，具名 Func 取 SQL 名（如 ReadCSV → READ_CSV）。"""
    if isinstance(node, exp.Anonymous):
        return str(node.name)
    if isinstance(node, exp.Func):
        try:
            return str(node.sql_name())
        except (AttributeError, TypeError):  # pragma: no cover - 极少见的自定义函数
            return type(node).__name__
    return ""


def validate_sql(sql: str) -> str:
    """校验并返回原 SQL；任何违规直接抛 SQL_REJECTED（含可读原因 + 修复建议）。"""
    if not isinstance(sql, str) or not sql.strip():
        raise _reject("SQL 为空", "请提供一条 SELECT 语句")
    if len(sql) > MAX_SQL_CHARS:
        raise _reject(
            f"SQL 长度 {len(sql)} 超过 {MAX_SQL_CHARS} 字符上限",
            "请拆分查询或减少注释",
        )

    try:
        statements = sqlglot.parse(sql, read="duckdb")
    except ParseError as exc:
        raise _reject(f"SQL 无法解析（{str(exc).splitlines()[0]}）", "请检查语法") from exc

    # 纯注释/结尾分号会被解析成 Semicolon 节点，不算第二条语句
    parsed = [
        stmt for stmt in statements if stmt is not None and not isinstance(stmt, exp.Semicolon)
    ]
    if len(parsed) != 1:
        raise _reject("只允许单条 SELECT 语句", "请移除多语句或写操作")
    statement = parsed[0]

    if not isinstance(statement, (exp.Select, exp.Union)):
        raise _reject("只允许 SELECT 查询（可含 WITH）", "请改写成 SELECT 语句")

    # CTE 名字在 AST 里也是 Table，必须放行，否则合法的 WITH 查询会被误杀
    cte_names = {cte.alias_or_name.strip().lower() for cte in statement.find_all(exp.CTE)}

    for node in statement.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise _reject(f"包含被禁止的语句类型 {type(node).__name__}", "请只提交只读查询")

        if isinstance(node, exp.Func) and _function_name(node).lower() in FORBIDDEN_FUNCTIONS:
            raise _reject(f"调用了被禁用的函数 {_function_name(node).lower()}", "只允许普通聚合与标量函数")

        if isinstance(node, exp.Table):
            table_name = _normalize_identifier(node.name or "")
            schema = _normalize_identifier(node.db or "")
            catalog = _normalize_identifier(node.catalog or "")
            qualified = ".".join(part for part in (catalog, schema, table_name) if part)

            if any(
                token in qualified for token in ("information_schema", "pg_catalog", "duckdb_")
            ):
                raise _reject(f"引用了系统对象 {qualified}", "只允许访问 data 视图")

            if not table_name:
                # 表函数（如 read_csv(...)）在 AST 里是没有名字的 Table
                function = next(
                    (sub for sub in node.walk() if isinstance(sub, exp.Func)), None
                )
                function_name = _function_name(function) if function is not None else ""
                if function_name.lower() in FORBIDDEN_FUNCTIONS:
                    raise _reject(
                        f"调用了被禁用的函数 {function_name.lower()}", "只允许 FROM data"
                    )
                raise _reject("查询了无法识别的表函数", f"请直接写 FROM {ALLOWED_TABLE}")

            if table_name in cte_names:
                continue

            if table_name != ALLOWED_TABLE:
                raise _reject(
                    f"引用了不允许的表 {qualified or table_name}",
                    f"只能查询视图 {ALLOWED_TABLE}（本数据集注册的唯一表）",
                )
            if schema not in ALLOWED_SCHEMAS or catalog:
                raise _reject(
                    f"表 {table_name} 使用了不允许的限定名 {catalog or schema}",
                    f"请直接写 {ALLOWED_TABLE}，不要带库名或 schema",
                )

        text = ""
        if isinstance(node, exp.Column):
            text = f"{node.table or ''}.{node.name or ''}".lower()
        if text and ("information_schema" in text or "pg_catalog" in text or "duckdb_" in text):
            raise _reject(f"引用了系统对象 {text}", "只允许访问 data 视图")

    return sql


def wrap_with_limit(sql: str, max_rows: int) -> str:
    """无论用户是否写 LIMIT，统一外层包一层，用 row_count 判断 truncated（规则 7）。"""
    safe_limit = max(int(max_rows), 1) + 1
    inner = sql.strip().rstrip(";")
    return f"SELECT * FROM ( {inner} ) AS _mm_sub LIMIT {safe_limit}"


def contains_forbidden_reference(raw_sql: str) -> bool:
    """兜底扫描（仅用于额外提示，不替代 AST 判定）。"""
    lowered = raw_sql.lower()
    return any(token in lowered for token in ("information_schema", "pg_catalog", "duckdb_"))
