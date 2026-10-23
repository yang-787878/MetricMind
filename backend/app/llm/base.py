"""LLM 客户端契约：只暴露"给系统提示 + 用户消息，要一段文本"这一件事。

为什么用 Protocol：Agent 节点不应感知具体厂商。Live 用 AsyncOpenAI（任意兼容服务），
Demo/测试用脚本化 Fake，两者行为一致，节点代码不需要分支。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class LLMResult:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    finish_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def truncated(self) -> bool:
        """模型因为 max_tokens 用尽而截断：这时候 JSON 一定是不完整的。"""
        return self.finish_reason == "length"


@dataclass
class LLMRequest:
    system: str
    user: str
    json_mode: bool = False
    temperature: float = 0.0
    max_tokens: int = 2048
    purpose: str = "generic"  # plan / repair / report，用于日志与用量归因


@runtime_checkable
class LLMClient(Protocol):
    model: str

    async def complete(self, request: LLMRequest) -> LLMResult: ...


class LLMError(Exception):
    """LLM 调用失败的统一异常：由节点决定降级策略。"""

    def __init__(self, message: str, *, code: str = "LLM_UNAVAILABLE", retryable: bool = True):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
