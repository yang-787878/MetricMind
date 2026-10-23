"""数据接入：上传校验 → 解析 → 列名规范化 → 语义类型推断 → 质量剖析 → 落库。

两条纪律：
1. 任何校验失败都抛带 code 的 AppError，message 面向用户、hint 面向修复。
2. 质量剖析只有一份实现（profile_frame），loader 落库与 profile_dataset 工具共用，
   避免"上传时显示的问题"和"Agent 看到的问题"不一致。
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ..config import Settings
from ..errors import AppError, ErrorCode
from ..logging_conf import get_logger
from ..models.enums import IssueSeverity, SemanticType, SourceKind
from .store import Store

logger = get_logger(__name__)

ALLOWED_EXTENSIONS = frozenset({".csv", ".xlsx"})
DATE_HINTS = ("date", "time", "day", "month", "week", "年", "月", "日", "时间")
MONEY_HINTS = ("price", "revenue", "cost", "amount", "spend", "profit", "金额", "价格", "成本")
ID_PATTERN = re.compile(r"(?:^|_)id$|(?:^|_)id_|(?:^|_)code$|编号|uuid", re.IGNORECASE)
OUTLIER_METHOD = "IQR 1.5"


def _utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_dataset_id() -> str:
    return f"ds_{uuid.uuid4().hex[:20]}"


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def normalize_columns(columns: list[Any]) -> tuple[list[str], dict[str, str]]:
    """列名规范化：去空白、空格/中文括号转下划线、去重加后缀、空列名 col_i。"""
    normalized: list[str] = []
    originals: dict[str, str] = {}
    for index, raw in enumerate(columns):
        text = "" if raw is None else str(raw)
        base = text.strip()
        base = re.sub(r"[\s\u3000]+", "_", base)
        base = base.replace("（", "(").replace("）", ")")
        base = re.sub(r"[()\u3010\u3011\[\]{}]", "_", base)
        base = re.sub(r"[^\w\u4e00-\u9fff]+", "_", base)
        base = re.sub(r"_+", "_", base).strip("_")
        if not base or base.lower() == "nan":
            base = f"col_{index}"
        candidate = base
        suffix = 2
        while candidate in originals:
            candidate = f"{base}_{suffix}"
            suffix += 1
        normalized.append(candidate)
        originals[candidate] = text
    return normalized, originals


def detect_encoding(path: Path) -> tuple[str, list[str]]:
    raw = path.read_bytes()[:65536]
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", []
    try:
        raw.decode("utf-8")
        return "utf-8", []
    except UnicodeDecodeError:
        pass
    try:
        raw.decode("gb18030")
        return "gb18030", ["文件不是 UTF-8 编码，已按 GB18030 解析，请确认中文没有乱码"]
    except UnicodeDecodeError:
        return "latin-1", ["文件编码无法识别，已按 Latin-1 解析，可能出现乱码"]


def _try_numeric(series: pd.Series) -> pd.Series | None:
    converted = pd.to_numeric(series, errors="coerce")
    original_non_null = int(series.notna().sum())
    if original_non_null == 0:
        return None
    parsed = int(converted.notna().sum())
    if parsed / original_non_null >= 0.95:
        return converted
    return None


def _looks_temporal(name: str, series: pd.Series) -> bool:
    lowered = name.lower()
    if any(hint in lowered for hint in DATE_HINTS):
        return True
    sample = series.dropna().astype(str).head(50)
    if sample.empty:
        return False
    parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    return float(parsed.notna().mean()) >= 0.9


def infer_semantic_type(name: str, series: pd.Series) -> SemanticType:
    """§8.7 规则：identifier → temporal → categorical → numeric/text。

    与任务书的差异：identifier 额外要求列名带 id/编号痕迹。
    否则"取值互不相同的整数指标"（例如小样本里的 revenue）会被误判成标识符。
    """
    non_null = series.dropna()
    unique_rate = float(non_null.nunique()) / max(len(non_null), 1)
    name_matches_id = bool(ID_PATTERN.search(str(name)))

    if pd.api.types.is_bool_dtype(series):
        return SemanticType.BOOLEAN

    if pd.api.types.is_integer_dtype(series) and unique_rate > 0.98 and name_matches_id:
        return SemanticType.IDENTIFIER

    if pd.api.types.is_datetime64_any_dtype(series):
        return SemanticType.TEMPORAL

    if pd.api.types.is_float_dtype(series) or pd.api.types.is_integer_dtype(series):
        return SemanticType.NUMERIC

    if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
        # 先判时间列：日期字符串的唯一率同样是 100%，若先判 identifier 会误分类
        if _looks_temporal(name, series):
            parsed = pd.to_datetime(non_null.astype(str), errors="coerce", format="mixed")
            uniques = int(non_null.nunique())
            hinted = any(hint in str(name).lower() for hint in DATE_HINTS)
            if float(parsed.notna().mean()) >= 0.9 and (uniques > 5 or (hinted and uniques >= 2)):
                return SemanticType.TEMPORAL
        if unique_rate > 0.98 and name_matches_id:
            return SemanticType.IDENTIFIER
        distinct = int(non_null.nunique())
        if distinct <= 50 or unique_rate < 0.2:
            return SemanticType.CATEGORICAL
        return SemanticType.TEXT

    return SemanticType.TEXT


def coerce_frame(df: pd.DataFrame, schema: list[dict[str, Any]]) -> pd.DataFrame:
    """按语义类型把字符串列转成数值/时间，保证 pandas 计算与 DuckDB 视图类型一致。"""
    frame = df.copy()
    for column in schema:
        name = column.get("name")
        if name not in frame.columns:
            continue
        semantic = column.get("semantic_type")
        if semantic == SemanticType.NUMERIC.value:
            frame[name] = pd.to_numeric(frame[name], errors="coerce")
        elif semantic == SemanticType.TEMPORAL.value:
            frame[name] = pd.to_datetime(frame[name], errors="coerce", format="mixed")
        elif semantic == SemanticType.BOOLEAN.value:
            frame[name] = frame[name].astype("boolean")
    return frame


def _is_textual(series: pd.Series) -> bool:
    """pandas 3 的字符串列是 `str` dtype 而不是 object，两类都要覆盖。"""
    if pd.api.types.is_bool_dtype(series) or pd.api.types.is_datetime64_any_dtype(series):
        return False
    if pd.api.types.is_numeric_dtype(series):
        return False
    return pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)


def _numeric_stats(series: pd.Series) -> dict[str, Any]:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return {
            "min": None, "max": None, "mean": None, "median": None, "p95": None,
            "zero_count": 0, "negative_count": 0, "outlier_count": 0,
        }
    q1 = float(numeric.quantile(0.25))
    q3 = float(numeric.quantile(0.75))
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    outliers = int(((numeric < lower) | (numeric > upper)).sum())
    return {
        "min": round(float(numeric.min()), 6),
        "max": round(float(numeric.max()), 6),
        "mean": round(float(numeric.mean()), 6),
        "median": round(float(numeric.median()), 6),
        "p95": round(float(numeric.quantile(0.95)), 6),
        "zero_count": int((numeric == 0).sum()),
        "negative_count": int((numeric < 0).sum()),
        "outlier_count": outliers if iqr > 0 else 0,
    }


def profile_frame(
    df: pd.DataFrame,
    columns: list[str] | None = None,
    include_outliers: bool = True,
) -> dict[str, Any]:
    """§5.2(2) 的确定性实现：一次遍历得到每列统计与固定集合的质量问题。"""
    selected = [c for c in (columns or list(df.columns)) if c in df.columns]
    row_count = int(len(df))
    duplicate_rows = int(df.duplicated().sum()) if row_count else 0
    issues: list[dict[str, Any]] = []
    column_reports: list[dict[str, Any]] = []

    for name in selected:
        series = df[name]
        null_count = int(series.isna().sum())
        non_null = series.dropna()
        distinct = int(non_null.nunique())
        report: dict[str, Any] = {
            "name": name,
            "null_count": null_count,
            "null_rate": round(null_count / row_count, 6) if row_count else 0.0,
            "distinct_count": distinct,
            "min": None, "max": None, "mean": None, "median": None, "p95": None,
            "zero_count": 0, "negative_count": 0, "outlier_count": 0,
        }

        is_numeric = pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)
        if is_numeric:
            stats = _numeric_stats(series)
            report.update(stats)
            if not include_outliers:
                report["outlier_count"] = 0
        elif pd.api.types.is_datetime64_any_dtype(series):
            if not non_null.empty:
                report["min"] = non_null.min().isoformat()
                report["max"] = non_null.max().isoformat()
        else:
            report["min"] = None if non_null.empty else str(non_null.min())
            report["max"] = None if non_null.empty else str(non_null.max())

        column_reports.append(report)

        if null_count > 0:
            severity = IssueSeverity.WARNING if report["null_rate"] >= 0.01 else IssueSeverity.INFO
            issues.append(
                {
                    "code": "NULL_VALUES",
                    "column": name,
                    "severity": severity.value,
                    "message": f"{name} 有 {null_count} 个空值（{report['null_rate'] * 100:.1f}%）",
                    "affected_rows": null_count,
                }
            )

        if distinct <= 1 and row_count > 1:
            issues.append(
                {
                    "code": "CONSTANT_COLUMN",
                    "column": name,
                    "severity": IssueSeverity.WARNING.value,
                    "message": f"{name} 只有一个取值，无法用于分组对比",
                    "affected_rows": row_count,
                }
            )

        if is_numeric and include_outliers and report["outlier_count"] > 0:
            issues.append(
                {
                    "code": "OUTLIERS_IQR",
                    "column": name,
                    "severity": IssueSeverity.INFO.value,
                    "message": (
                        f"{name} 有 {report['outlier_count']} 个异常值（{OUTLIER_METHOD} 判定，"
                        f"区间外）"
                    ),
                    "affected_rows": report["outlier_count"],
                }
            )

        if is_numeric and (report["negative_count"] > 0 or (
            report["zero_count"] > 0 and any(h in name.lower() for h in MONEY_HINTS)
        )):
            affected = report["negative_count"] + report["zero_count"]
            issues.append(
                {
                    "code": "ZERO_OR_NEGATIVE",
                    "column": name,
                    "severity": IssueSeverity.WARNING.value,
                    "message": (
                        f"{name} 有 {report['zero_count']} 个 0 与 {report['negative_count']} 个负值，"
                        "可能影响比率类结论"
                    ),
                    "affected_rows": affected,
                }
            )

        if _is_textual(series) and row_count > 0:
            unique_rate = distinct / max(len(non_null), 1)
            if unique_rate > 0.98 and "id" in name.lower():
                issues.append(
                    {
                        "code": "HIGH_CARDINALITY",
                        "column": name,
                        "severity": IssueSeverity.INFO.value,
                        "message": f"{name} 唯一率 {unique_rate:.0%}，作为维度会非常稀疏",
                        "affected_rows": distinct,
                    }
                )
            numeric_guess = _try_numeric(series)
            if numeric_guess is not None and null_count == 0 and numeric_guess.isna().sum() > 0:
                issues.append(
                    {
                        "code": "TYPE_MIXED",
                        "column": name,
                        "severity": IssueSeverity.WARNING.value,
                        "message": f"{name} 混有无法解析为数字的文本，已按空值处理",
                        "affected_rows": int(numeric_guess.isna().sum()),
                    }
                )

        if any(hint in name.lower() for hint in DATE_HINTS):
            sample = non_null.astype(str).head(200)
            if not sample.empty:
                parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
                failed = int(parsed.isna().sum())
                if failed > 0:
                    issues.append(
                        {
                            "code": "DATE_UNPARSEABLE",
                            "column": name,
                            "severity": IssueSeverity.ERROR.value,
                            "message": f"{name} 有 {failed} 个值无法解析为日期，时间趋势结论不可信",
                            "affected_rows": failed,
                        }
                    )

    if duplicate_rows > 0:
        issues.insert(
            0,
            {
                "code": "DUPLICATE_ROWS",
                "column": None,
                "severity": IssueSeverity.WARNING.value,
                "message": f"存在 {duplicate_rows} 行完全重复的记录",
                "affected_rows": duplicate_rows,
            },
        )

    return {
        "row_count": row_count,
        "duplicate_rows": duplicate_rows,
        "columns": column_reports,
        "issues": issues,
        "method": OUTLIER_METHOD,
    }


def _read_csv_header(path: Path, encoding: str) -> list[str]:
    """直接读第一行原文：pandas 会自动把重名列改成 a/a.1，掩盖表头重复问题。"""
    with path.open("r", encoding=encoding, newline="") as handle:
        first_line = handle.readline()
    if not first_line.strip():
        return []
    return next(csv.reader([first_line]), [])


def _read_raw(path: Path, ext: str) -> tuple[pd.DataFrame, str, list[str]]:
    warnings: list[str] = []
    if ext == ".xlsx":
        frame = pd.read_excel(path, engine="openpyxl")
        return frame, "binary-xlsx", warnings
    encoding, encoding_warnings = detect_encoding(path)
    warnings.extend(encoding_warnings)
    frame = pd.read_csv(path, encoding=encoding, keep_default_na=True, na_values=["", "NULL", "null"])
    return frame, encoding, warnings


def _schema_from_frame(frame: pd.DataFrame, originals: dict[str, str]) -> list[dict[str, Any]]:
    schema: list[dict[str, Any]] = []
    for name in frame.columns:
        series = frame[name]
        semantic = infer_semantic_type(str(name), series)
        non_null = series.dropna()
        entry: dict[str, Any] = {
            "name": name,
            "original_name": originals.get(name, name),
            "dtype": str(series.dtype),
            "semantic_type": semantic.value,
            "null_rate": round(float(series.isna().mean()), 6) if len(series) else 0.0,
            "distinct_count": int(non_null.nunique()),
            "sample_values": [None if pd.isna(v) else v for v in non_null.head(3).tolist()],
            "stats": None,
        }
        if semantic == SemanticType.NUMERIC:
            stats = _numeric_stats(series)
            entry["stats"] = {
                "min": stats["min"], "max": stats["max"],
                "mean": stats["mean"], "median": stats["median"],
            }
        schema.append(entry)
    return schema


class DatasetLoader:
    def __init__(self, store: Store, settings: Settings) -> None:
        self.store = store
        self.settings = settings

    # ---------------- 上传 ----------------
    def create_from_upload(self, filename: str, content: bytes) -> dict[str, Any]:
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise AppError(
                ErrorCode.UNSUPPORTED_FILE_TYPE,
                f"不支持的文件类型 {ext or '(无扩展名)'}，仅支持 CSV / XLSX",
                details={"filename": filename},
                hint="请上传 .csv 或 .xlsx 文件",
            )
        limit_bytes = self.settings.max_upload_mb * 1024 * 1024
        if len(content) > limit_bytes:
            raise AppError(
                ErrorCode.FILE_TOO_LARGE,
                f"文件 {len(content) / 1024 / 1024:.1f} MB 超过 {self.settings.max_upload_mb} MB 限制",
                details={"size_bytes": len(content), "max_bytes": limit_bytes},
            )
        if not content:
            raise AppError(ErrorCode.INVALID_DATASET, "文件为空", hint="请上传包含表头与数据的文件")

        dataset_id = new_dataset_id()
        self.settings.ensure_dirs()
        stored_path = self.settings.uploads_dir / f"{dataset_id}{ext}"
        stored_path.write_bytes(content)

        name = Path(filename).stem or dataset_id
        return self._ingest(
            dataset_id=dataset_id,
            stored_path=stored_path,
            ext=ext,
            name=name,
            original_filename=filename,
            source=SourceKind.UPLOAD,
            size_bytes=len(content),
            checksum=sha256_bytes(content),
        )

    # ---------------- 示例数据 ----------------
    def sample_registry(self) -> list[dict[str, Any]]:
        path = self.settings.samples_registry
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        samples = payload.get("samples", payload) if isinstance(payload, dict) else payload
        return samples if isinstance(samples, list) else []

    def create_from_sample(self, key: str) -> tuple[dict[str, Any], bool]:
        entry = next((item for item in self.sample_registry() if item.get("key") == key), None)
        if entry is None:
            raise AppError(
                ErrorCode.NOT_FOUND,
                f"示例数据集 {key} 不存在",
                details={"key": key},
            )
        filename = entry.get("filename", f"{key}.csv")
        path = self.settings.samples_dir / filename
        if not path.exists():
            raise AppError(
                ErrorCode.DATASET_NOT_FOUND,
                f"示例数据文件 {filename} 尚未生成",
                hint="请先运行 python scripts/generate_sample_data.py",
            )
        content = path.read_bytes()
        checksum = sha256_bytes(content)
        existing = self.store.find_dataset_by_checksum(checksum)
        if existing:
            return existing, True

        ext = path.suffix.lower()
        dataset_id = new_dataset_id()
        self.settings.ensure_dirs()
        stored_path = self.settings.uploads_dir / f"{dataset_id}{ext}"
        stored_path.write_bytes(content)
        row = self._ingest(
            dataset_id=dataset_id,
            stored_path=stored_path,
            ext=ext,
            name=entry.get("name", key),
            original_filename=filename,
            source=SourceKind.SAMPLE,
            size_bytes=len(content),
            checksum=checksum,
        )
        return row, False

    # ---------------- 通用解析 ----------------
    def _ingest(
        self,
        *,
        dataset_id: str,
        stored_path: Path,
        ext: str,
        name: str,
        original_filename: str,
        source: SourceKind,
        size_bytes: int,
        checksum: str,
    ) -> dict[str, Any]:
        frame, encoding, warnings = _read_raw(stored_path, ext)
        if ext == ".csv":
            try:
                headers = _read_csv_header(stored_path, encoding)
            except (OSError, UnicodeDecodeError):
                headers = []
            duplicates = sorted(
                {name for name in headers if headers.count(name) > 1 and name.strip()}
            )
            if duplicates:
                stored_path.unlink(missing_ok=True)
                raise AppError(
                    ErrorCode.INVALID_DATASET,
                    f"表头存在重复列名：{duplicates}",
                    details={"duplicate_columns": duplicates},
                    hint="请先重命名重复列后再上传",
                )
        raw_columns = [str(c) for c in frame.columns]
        duplicated = sorted({c for c in raw_columns if raw_columns.count(c) > 1})
        if duplicated:
            stored_path.unlink(missing_ok=True)
            raise AppError(
                ErrorCode.INVALID_DATASET,
                f"表头存在重复列名：{duplicated}",
                details={"duplicate_columns": duplicated},
                hint="请先重命名重复列后再上传",
            )
        if frame.empty:
            stored_path.unlink(missing_ok=True)
            raise AppError(ErrorCode.INVALID_DATASET, "文件没有数据行", hint="请检查表头与内容")
        if len(frame) > self.settings.max_rows:
            stored_path.unlink(missing_ok=True)
            raise AppError(
                ErrorCode.DATASET_TOO_LARGE,
                f"数据有 {len(frame)} 行，超过 {self.settings.max_rows} 行上限",
                details={"row_count": len(frame), "max_rows": self.settings.max_rows},
                hint="请先聚合或抽样后再上传",
            )
        if len(frame.columns) > self.settings.max_columns:
            stored_path.unlink(missing_ok=True)
            raise AppError(
                ErrorCode.DATASET_TOO_LARGE,
                f"数据有 {len(frame.columns)} 列，超过 {self.settings.max_columns} 列上限",
                details={"column_count": len(frame.columns)},
            )

        normalized, originals = normalize_columns(list(frame.columns))
        frame.columns = normalized

        schema = _schema_from_frame(frame, originals)
        prepared = coerce_frame(frame, schema)
        profile = profile_frame(prepared)
        quality = {
            "duplicate_row_count": profile["duplicate_rows"],
            "row_count_after_dedup": profile["row_count"] - profile["duplicate_rows"],
            "issues": profile["issues"],
        }

        row = {
            "dataset_id": dataset_id,
            "name": name,
            "original_filename": original_filename,
            "source": source.value,
            "stored_path": str(stored_path),
            "row_count": int(len(prepared)),
            "column_count": int(len(prepared.columns)),
            "size_bytes": size_bytes,
            "checksum": checksum,
            "schema_json": json.dumps(schema, ensure_ascii=False),
            "quality_json": json.dumps(quality, ensure_ascii=False),
            "encoding": encoding,
            "created_at": _utcnow(),
        }
        self.store.insert_dataset(row)
        logger.info(
            "dataset_ingested",
            extra={
                "dataset_id": dataset_id,
                "rows": row["row_count"],
                "columns": row["column_count"],
                "source": row["source"],
                "warnings": warnings,
            },
        )
        return row

    # ---------------- 读取 ----------------
    def load_frame(self, row: dict[str, Any]) -> pd.DataFrame:
        path = Path(row["stored_path"])
        if not path.exists():
            raise AppError(
                ErrorCode.DATASET_NOT_FOUND,
                "数据集文件已丢失，请重新上传",
                details={"dataset_id": row["dataset_id"]},
            )
        ext = path.suffix.lower()
        frame, _, _ = _read_raw(path, ext)
        normalized, _ = normalize_columns(list(frame.columns))
        frame.columns = normalized
        schema = json.loads(row["schema_json"])
        return coerce_frame(frame, schema)

    def preview(self, row: dict[str, Any], limit: int = 50) -> dict[str, Any]:
        frame = self.load_frame(row)
        head = frame.head(limit)
        columns = [
            {"name": name, "type": str(head[name].dtype)}
            for name in head.columns
        ]
        rows = [
            [_jsonable(value) for value in record]
            for record in head.itertuples(index=False, name=None)
        ]
        return {"columns": columns, "rows": rows, "total_rows": int(len(frame))}

    def dataset_detail(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "dataset_id": row["dataset_id"],
            "name": row["name"],
            "original_filename": row["original_filename"],
            "source": row["source"],
            "row_count": row["row_count"],
            "column_count": row["column_count"],
            "size_bytes": row["size_bytes"],
            "created_at": row["created_at"],
            "checksum": row["checksum"],
            "encoding": row.get("encoding"),
            "columns": json.loads(row["schema_json"]),
            "quality": json.loads(row["quality_json"]),
        }


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            return str(value)
    return value
