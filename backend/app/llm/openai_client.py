"""真实 LLM：OpenAI 兼容接口（OpenAI / DeepSeek / Moonshot / 通义 / vLLM…）。

三个硬要求：
1. 模型名、base_url 都来自配置，不硬编码；
2. 超时 / 429 / 5xx 走指数退避（0.5s / 1.5s / 4s + 抖动），最多重试 2 次；
3. 只记录前 500 字符摘要，绝不记录完整响应与 API Key。
"""

from __future__ import annotations

import asyncio
import random
import time

from openai import AsyncOpenAI
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from ..logging_conf import get_logger
from .base import LLMError, LLMRequest, LLMResult

logger = get_logger(__name__)

BACKOFF_SECONDS = (0.5, 1.5, 4.0)
RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})


class OpenAIClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_s: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        if not api_key:
            raise LLMError("未配置 OPENAI_API_KEY", code="LLM_NOT_CONFIGURED", retryable=False)
        self.model = model
        self.max_retries = max_retries
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout_s)

    async def complete(self, request: LLMRequest) -> LLMResult:
        messages = [
            {"role": "system", "content": request.system},
            {"role": "user", "content": request.user},
        ]
        attempt = 0
        last_error: Exception | None = None

        while attempt <= self.max_retries:
            started = time.perf_counter()
            try:
                payload: dict[str, object] = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": request.temperature,
                    "max_tokens": request.max_tokens,
                }
                if request.json_mode:
                    payload["response_format"] = {"type": "json_object"}
                response = await self._client.chat.completions.create(**payload)
                latency_ms = int((time.perf_counter() - started) * 1000)
                content = response.choices[0].message.content or ""
                finish_reason = getattr(response.choices[0], "finish_reason", None)
                usage = response.usage
                logger.info(
                    "llm_call",
                    extra={
                        "purpose": request.purpose,
                        "model": self.model,
                        "latency_ms": latency_ms,
                        "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                        "completion_tokens": getattr(usage, "completion_tokens", 0),
                        "attempt": attempt,
                        "preview": content[:500],
                    },
                )
                return LLMResult(
                    text=content,
                    model=self.model,
                    prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                    completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
                    latency_ms=latency_ms,
                    finish_reason=finish_reason,
                )
            except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
                last_error = exc
                retryable = True
            except APIStatusError as exc:
                last_error = exc
                retryable = exc.status_code in RETRYABLE_STATUS
            except Exception as exc:  # pragma: no cover - SDK 之外的意外
                raise LLMError(f"LLM 调用失败：{exc}") from exc

            if not retryable:
                raise LLMError(f"LLM 返回不可重试错误：{last_error}")
            attempt += 1
            if attempt > self.max_retries:
                break
            delay = BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)]
            await asyncio.sleep(delay + random.uniform(0, 0.25))
            logger.warning(
                "llm_retry",
                extra={"purpose": request.purpose, "attempt": attempt, "error": str(last_error)[:200]},
            )

        raise LLMError(f"LLM 连续失败：{last_error}")
