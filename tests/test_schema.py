"""Tests for the audit schema and response parsing.

This module existed untested while every headline number in the project flowed through it. A
boolean-coercion bug here inverted every negative verdict the baseline produced, which made the
baseline look like an indiscriminate flag-everything system and inflated the reported improvement.
The bug was invisible because the corrupted values were still *plausible*.

The lesson generalises: parsing code that sits between a model and a metric needs the same
scrutiny as the metric.
"""

from __future__ import annotations

import json

import pytest

from rewardgate.schema import (
    ACCEPT,
    CONTAMINATION_GIT,
    DEFECT_CLASSES,
    NOP_PASS,
    REWARD_HACKABLE,
    Audit,
    coerce_bool,
    parse_audit,
    schema_instructions,
)


@pytest.mark.parametrize("value", [False, "false", "False", "FALSE", "no", "0", 0, None, "", "maybe"])
def test_falsey_values_do_not_become_true(value):
    """`bool("false")` is True. That single fact invalidated an entire evaluation run."""
    assert coerce_bool(value) is False


@pytest.mark.parametrize("value", [True, "true", "True", "TRUE", "yes", "1", 1, "detected"])
def test_truthy_values_are_recognised(value):
    assert coerce_bool(value) is True


def test_unrecognised_values_default_to_no_defect():
    """A system that cannot state a defect clearly has not established one."""
    assert coerce_bool(["unexpected"]) is False
    assert coerce_bool({"a": 1}) is False


def test_prompt_template_asks_for_real_booleans_not_strings():
    """Regression: the template once showed "true|false", so the model returned a string."""
    instructions = schema_instructions()
    assert "true|false" not in instructions
    assert "must be a JSON boolean" in instructions
    start, end = instructions.find("{"), instructions.rfind("}")
    example = json.loads(instructions[start : end + 1])
    for defect in DEFECT_CLASSES:
        assert example["defects"][defect] is False


def test_string_false_response_is_parsed_as_no_defect():
    raw = json.dumps({"defects": {d: "false" for d in DEFECT_CLASSES}, "verdict": ACCEPT})
    audit = parse_audit("b", raw)
    assert not audit.any_defect
    assert all(audit.flags(d) is False for d in DEFECT_CLASSES)


def test_boolean_response_is_parsed_faithfully():
    raw = json.dumps(
        {
            "defects": {NOP_PASS: True, REWARD_HACKABLE: False, CONTAMINATION_GIT: False},
            "verdict": "REJECT",
        }
    )
    audit = parse_audit("b", raw)
    assert audit.flags(NOP_PASS)
    assert not audit.flags(REWARD_HACKABLE)
    assert audit.verdict == "REJECT"


def test_mixed_string_and_boolean_values_are_each_handled():
    raw = json.dumps(
        {
            "defects": {NOP_PASS: "true", REWARD_HACKABLE: False, CONTAMINATION_GIT: "no"},
            "verdict": "REVISE",
        }
    )
    audit = parse_audit("b", raw)
    assert audit.flags(NOP_PASS)
    assert not audit.flags(REWARD_HACKABLE)
    assert not audit.flags(CONTAMINATION_GIT)


def test_json_wrapped_in_prose_or_fences_is_recovered():
    raw = "Here is my audit:\n```json\n" + json.dumps(
        {"defects": {d: False for d in DEFECT_CLASSES}, "verdict": ACCEPT}
    ) + "\n```\nHope that helps."
    assert not parse_audit("b", raw).any_defect


def test_missing_defect_key_is_absent_not_present():
    audit = parse_audit("b", json.dumps({"defects": {NOP_PASS: True}, "verdict": "REJECT"}))
    assert audit.flags(NOP_PASS)
    assert not audit.flags(REWARD_HACKABLE)


@pytest.mark.parametrize("raw", ["", "   ", "no json here", "{broken"])
def test_unusable_responses_yield_an_error_audit_asserting_nothing(raw):
    """A crashed run must score as a miss, never be silently credited with a correct answer."""
    audit = parse_audit("b", raw)
    assert audit.error
    assert not audit.any_defect


def test_empty_audit_asserts_no_defects():
    audit = Audit.empty("b", error="boom")
    assert not audit.any_defect
    assert audit.verdict == ACCEPT
    assert audit.error == "boom"
