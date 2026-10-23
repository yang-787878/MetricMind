"""数字溯源校验单测（§10.1 第 7 条）。"""

from __future__ import annotations

import pytest

from app.services.verifier import ClaimInput, verify_claims


def _evidence(**values: float) -> dict:
    return {"data": {"metrics": [{"name": key, "value": value} for key, value in values.items()]}}


def _resolver(mapping: dict[str, dict]):
    return lambda result_id: mapping.get(result_id)


def claim(claim_id: str, values: list[tuple[float, str]], evidence: list[str]) -> ClaimInput:
    return ClaimInput(
        claim_id=claim_id,
        text=f"claim {claim_id}",
        numbers=[{"value": value, "unit": unit} for value, unit in values],
        evidence_ids=evidence,
    )


def test_exact_match_is_supported() -> None:
    result = verify_claims(
        [claim("c1", [(1042180.0, "CNY")], ["res_1"])],
        _resolver({"res_1": _evidence(revenue=1042180.0)}),
    )
    assert result.coverage == pytest.approx(1.0)
    assert result.items[0].status == "supported"
    assert result.items[0].matched_value == pytest.approx(1042180.0)


def test_two_percent_off_is_unsupported_with_closest_value() -> None:
    result = verify_claims(
        [claim("c1", [(102.0, "CNY")], ["res_1"])],
        _resolver({"res_1": _evidence(revenue=100.0)}),
    )
    assert result.items[0].status == "unsupported"
    assert result.items[0].matched_value == pytest.approx(100.0)
    assert "接近但超差" in result.items[0].reason


def test_missing_evidence_is_unsupported() -> None:
    result = verify_claims([claim("c1", [(1.0, "")], [])], _resolver({}))
    assert result.items[0].status == "unsupported"
    assert result.items[0].reason == "未提供证据"


def test_unknown_result_id_is_unsupported() -> None:
    result = verify_claims([claim("c1", [(1.0, "")], ["res_missing"])], _resolver({}))
    assert result.items[0].status == "unsupported"
    assert "证据不存在" in result.items[0].reason


def test_percent_and_decimal_are_interchangeable() -> None:
    result = verify_claims(
        [claim("c1", [(-18.4, "%")], ["res_1"])],
        _resolver({"res_1": _evidence(growth=-0.184)}),
    )
    assert result.items[0].status == "supported"


def test_one_bad_number_breaks_whole_claim() -> None:
    result = verify_claims(
        [claim("c1", [(100.0, "CNY"), (999.0, "CNY")], ["res_1"])],
        _resolver({"res_1": _evidence(revenue=100.0)}),
    )
    assert result.items[0].status == "unsupported"
    assert result.items[0].claimed_value == pytest.approx(999.0)


def test_no_candidate_numbers_is_unverifiable() -> None:
    result = verify_claims(
        [claim("c1", [(5.0, "")], ["res_1"])],
        _resolver({"res_1": {"data": {"columns": [{"name": "channel"}]}}}),
    )
    assert result.items[0].status == "unverifiable"


def test_coverage_counts_supported_only() -> None:
    result = verify_claims(
        [
            claim("c1", [(100.0, "CNY")], ["res_1"]),
            claim("c2", [(999.0, "CNY")], ["res_1"]),
            claim("c3", [(1.0, "")], []),
            claim("c4", [(2.0, "")], ["res_missing"]),
        ],
        _resolver({"res_1": _evidence(revenue=100.0)}),
    )
    assert result.supported == 1
    # c2 数字超差、c3 未提供证据、c4 证据不存在：都算 unsupported（§5.2(6) 第 4 条）
    assert result.unsupported == 3
    assert result.unverifiable == 0
    assert result.coverage == pytest.approx(0.25)


def test_tables_cells_are_candidates() -> None:
    payload = {"data": {"columns": [{"name": "revenue"}], "rows": [[1234.5], [2.0]]}}
    result = verify_claims(
        [claim("c1", [(1234.5, "CNY")], ["res_1"])], _resolver({"res_1": payload})
    )
    assert result.items[0].status == "supported"
