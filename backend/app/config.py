"""集中式配置：所有环境变量只有在这里读取一次，其余模块从 Settings 取。

为什么不用散落的 os.environ：限额、路径、LLM 模式在 API、runner、工具层都要用，
集中校验可以保证非法值在启动时就失败，而不是在某个工具执行到一半时抛异常。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> backend/app -> backend -> <repo root>
ROOT_DIR = Path(__file__).resolve().parents[2]

LLMMode = Literal["auto", "live", "demo"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(ROOT_DIR / ".env"), str(ROOT_DIR / "backend" / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "MetricMind"
    version: str = "1.0.0"
    api_prefix: str = "/api"

    # --- LLM ---
    llm_mode: LLMMode = "auto"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    llm_timeout_s: float = 60.0
    llm_max_retries: int = 2
    # 单次输出的 token 上限：计划/报告是长 JSON，太小会被截断（DeepSeek 上实测过）
    llm_max_output_tokens: int = 4096

    # --- storage ---
    data_dir: str = "backend/data"
    db_path: str = "backend/data/metricmind.db"

    # --- limits ---
    max_upload_mb: int = 25
    max_rows: int = 200_000
    max_columns: int = 60
    max_steps: int = 10
    max_tool_calls: int = 16
    max_replans: int = 2
    run_timeout_s: int = 240
    max_concurrent_runs: int = 2
    rate_limit_per_minute: int = 6
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    # --- verification thresholds (见 docs/ARCHITECTURE.md) ---
    support_tolerance: float = 0.005
    near_tolerance: float = 0.01
    min_coverage: float = 0.9

    @field_validator("max_upload_mb", "max_rows", "max_columns", "max_steps", "max_tool_calls")
    @classmethod
    def _positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("limit must be positive")
        return value

    @field_validator("llm_max_output_tokens")
    @classmethod
    def _positive_tokens(cls, value: int) -> int:
        if value < 256:
            raise ValueError("LLM_MAX_OUTPUT_TOKENS 至少 256")
        return value

    @field_validator("max_replans")
    @classmethod
    def _non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("max_replans must be >= 0")
        return value

    # --- 派生路径 ---
    def _resolve(self, raw: str) -> Path:
        path = Path(raw)
        return path if path.is_absolute() else (ROOT_DIR / path)

    @property
    def data_path(self) -> Path:
        return self._resolve(self.data_dir)

    @property
    def db_file(self) -> Path:
        return self._resolve(self.db_path)

    @property
    def uploads_dir(self) -> Path:
        return self.data_path / "uploads"

    @property
    def exports_dir(self) -> Path:
        return self.data_path / "exports"

    @property
    def samples_dir(self) -> Path:
        return ROOT_DIR / "data"

    @property
    def samples_registry(self) -> Path:
        return self.samples_dir / "samples.json"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def has_api_key(self) -> bool:
        return bool(self.openai_api_key.strip())

    @property
    def resolved_llm_mode(self) -> Literal["live", "demo"]:
        """`auto` 只是入口语义，对外始终暴露 live/demo 两种真实模式。"""
        if self.llm_mode == "live":
            return "live" if self.has_api_key else "demo"
        if self.llm_mode == "demo":
            return "demo"
        return "live" if self.has_api_key else "demo"

    def ensure_dirs(self) -> None:
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
