"""提示词加载：.md 文件是唯一来源，代码里不内联提示词文本。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


@lru_cache(maxsize=8)
def load_prompt(name: str) -> str:
    path = PROMPT_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"缺少提示词模板：{path}")
    return path.read_text(encoding="utf-8")
