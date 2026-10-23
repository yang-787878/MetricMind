"""结构化分析计划模型（§4.2 分析计划）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(pattern=r"^s[0-9]{1,3}$")
    title: str = Field(min_length=1, max_length=120)
    intent: str = Field(default="", max_length=400)
    tool: str = Field(min_length=1)
    tool_args_hint: dict[str, Any] = Field(default_factory=dict)
    expected_output: str = Field(default="", max_length=400)
    validation: str = Field(default="", max_length=400)


class StructuredPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=1, max_length=400)
    required_fields: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    steps: list[PlanStep] = Field(min_length=1)
    risks: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    plan_version: int = 1
    narrative_source: str | None = None  # "llm" | "template"，Demo 模式必须为 template
