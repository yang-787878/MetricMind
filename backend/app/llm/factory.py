"""按配置装配 LLM 客户端：demo 模式不构造真实客户端，也不允许偷偷调用模型。"""

from __future__ import annotations

from ..config import Settings
from .base import LLMClient, LLMError, LLMRequest, LLMResult
from .openai_client import OpenAIClient


class DemoLLM:
    """Demo 模式的占位客户端：被调用即报错，避免"Demo 却悄悄用了模型"的假象。"""

    model = "demo-template"

    async def complete(self, request: LLMRequest) -> LLMResult:
        raise LLMError(
            f"Demo 模式不调用大模型（purpose={request.purpose}）",
            code="LLM_NOT_CONFIGURED",
            retryable=False,
        )


def build_llm(settings: Settings, mode: str | None = None) -> LLMClient:
    resolved = mode or settings.resolved_llm_mode
    if resolved == "demo" or not settings.has_api_key:
        return DemoLLM()
    return OpenAIClient(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.llm_model,
        timeout_s=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
    )
