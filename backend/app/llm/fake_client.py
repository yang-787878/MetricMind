"""测试用脚本化 LLM：按调用顺序返回预设内容，并记录收到的请求。

`responses` 的元素可以是字符串，也可以是 `Callable[[LLMRequest], str]`——
后者让测试能在"报告阶段"读取真实证据再构造 claims，这样审计链路才是真跑通的，
而不是把数字硬编码在测试里绕过校验。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .base import LLMError, LLMRequest, LLMResult

Response = str | Callable[[LLMRequest], str]


@dataclass
class FakeLLM:
    responses: list[Response] = field(default_factory=list)
    model: str = "fake-llm"
    requests: list[LLMRequest] = field(default_factory=list)
    default_response: Response | None = None

    async def complete(self, request: LLMRequest) -> LLMResult:
        self.requests.append(request)
        if self.responses:
            item = self.responses.pop(0)
        elif self.default_response is not None:
            item = self.default_response
        else:
            raise LLMError("FakeLLM 没有更多预设响应", retryable=False)
        text = item(request) if callable(item) else item
        return LLMResult(
            text=text,
            model=self.model,
            prompt_tokens=len(request.system) // 4 + len(request.user) // 4,
            completion_tokens=len(text) // 4,
            latency_ms=1,
            finish_reason="stop",
        )

    @property
    def calls(self) -> int:
        return len(self.requests)
