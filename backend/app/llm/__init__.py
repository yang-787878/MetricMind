"""LLM 包：客户端实现 + 提示词模板 + 工厂。"""

from .base import LLMClient, LLMError, LLMRequest, LLMResult
from .factory import build_llm

__all__ = ["LLMClient", "LLMError", "LLMRequest", "LLMResult", "build_llm"]
