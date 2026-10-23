"""数字溯源校验（§5.2(6) / §6.4 第三道关卡）。

判定是确定性的：从证据 payload 递归取数 → 归一化 → 容差匹配。
阈值写成常量，文档里出现的 0.5% 与代码里的 RELATIVE_TOLERANCE 必须一致。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..logging_conf import get_logger
from ..models.enums import VerificationStatus
from ..models.tool import VerificationItem, VerificationResult
from .jsonable import to_jsonable

logger = get_logger(__name__)

RELATIVE_TOLERANCE = 0.005  # |claimed - v| <= 0.5% * |v| → supported
NEAR_TOLERANCE = 0.01  # 1% 以内但超出 0.5% → unsupported（接近但超差）
EPSILON = 1e-9


@dataclass
class ClaimInput:
    claim_id: str
    text: str
    numbers: list[dict[str, float | str]]
    evidence_ids: list[str]


def normalize(value: float, unit: str | None) -> float:
    """去掉千分位/百分号；% 与小数互认（-18.4% → -0.184）。"""
    number = float(value)
    if unit and unit.strip() == "%":
        number = number / 100.0
    return round(number, 6)


def _variants(candidate: float) -> list[float]:
    """同一证据值可能以小数或百分数出现，两种形态都参与匹配。"""
    return [candidate, candidate / 100.0, candidate * 100.0]


def _match(claimed: float, candidates: list[float]) -> tuple[str, float | None]:
    """有候选值就一定能给出结论：命中 → supported，否则 unsupported + 最接近值。"""
    best: float | None = None
    best_delta: float | None = None
    for candidate in candidates:
        for variant in _variants(candidate):
            delta = abs(claimed - variant)
            if best_delta is None or delta < best_delta:
                best, best_delta = variant, delta
            if delta <= max(RELATIVE_TOLERANCE * abs(variant), EPSILON):
                return VerificationStatus.SUPPORTED.value, variant
    return VerificationStatus.UNSUPPORTED.value, best


def verify_claims(
    claims: list[ClaimInput],
    resolve_evidence,
) -> VerificationResult:
    """逐条 claim 校验；同一 claim 内任一数字不通过即整条 unsupported。"""
    items: list[VerificationItem] = []
    for claim in claims:
        candidates: list[float] = []
        used_evidence: str | None = None
        missing: list[str] = []

        for evidence_id in claim.evidence_ids or []:
            payload = resolve_evidence(evidence_id)
            if payload is None:
                missing.append(evidence_id)
                continue
            from .evidence import extract_numbers  # 局部导入避免循环依赖

            candidates.extend(extract_numbers(payload.get("data")))
            used_evidence = used_evidence or evidence_id

        if not claim.evidence_ids:
            items.append(
                VerificationItem(
                    claim_id=claim.claim_id,
                    status=VerificationStatus.UNSUPPORTED.value,
                    reason="未提供证据",
                    claimed_value=None,
                )
            )
            continue
        if not candidates:
            status = (
                VerificationStatus.UNVERIFIABLE.value
                if used_evidence
                else VerificationStatus.UNSUPPORTED.value
            )
            items.append(
                VerificationItem(
                    claim_id=claim.claim_id,
                    status=status,
                    reason=(
                        "证据中没有可核对的数值"
                        if used_evidence
                        else f"证据不存在：{', '.join(missing) or '无'}"
                    ),
                    claimed_value=None,
                )
            )
            continue

        status = VerificationStatus.SUPPORTED.value
        matched_value: float | None = None
        matched_evidence: str | None = used_evidence
        first_failure: str | None = None
        claimed_value: float | None = None
        relative_delta: float | None = None

        for number in claim.numbers:
            raw = float(number.get("value", 0.0))
            unit = str(number.get("unit") or "")
            claimed = normalize(raw, unit)
            claimed_value = claimed
            item_status, best = _match(claimed, candidates)
            if item_status == VerificationStatus.SUPPORTED.value:
                matched_value = best
                continue
            status = item_status
            matched_value = best
            if best is not None and best != 0:
                relative_delta = round(abs(claimed - best) / abs(best), 6)
            if item_status == VerificationStatus.UNSUPPORTED.value:
                first_failure = (
                    f"接近但超差，最接近值 {best}" if best is not None else "未找到匹配数字"
                )
            else:
                first_failure = f"无法验证，最接近值 {best}" if best is not None else "未找到匹配数字"
            break

        items.append(
            VerificationItem(
                claim_id=claim.claim_id,
                status=status,
                matched_evidence_id=matched_evidence,
                matched_value=to_jsonable(matched_value),
                claimed_value=to_jsonable(claimed_value),
                relative_delta=relative_delta,
                reason=first_failure or "",
            )
        )

    total = len(items)
    supported = sum(1 for item in items if item.status == VerificationStatus.SUPPORTED.value)
    unsupported = sum(1 for item in items if item.status == VerificationStatus.UNSUPPORTED.value)
    unverifiable = sum(
        1 for item in items if item.status == VerificationStatus.UNVERIFIABLE.value
    )
    coverage = round(supported / total, 6) if total else 0.0
    return VerificationResult(
        coverage=coverage,
        items=items,
        supported=supported,
        unsupported=unsupported,
        unverifiable=unverifiable,
    )
