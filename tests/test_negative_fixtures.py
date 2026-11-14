import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_negative_fixtures as negative


def test_must_fail_requires_nonzero_exit_and_text():
    ok, missing = negative.evaluate(1, "name is required\n", True, ["name is required"])
    assert ok and missing == []

    ok, missing = negative.evaluate(1, "something else\n", True, ["name is required"])
    assert not ok
    assert missing == ["name is required"]

    ok, missing = negative.evaluate(0, "name is required\n", True, ["name is required"])
    assert not ok
    assert missing == []


def test_must_pass_rejects_a_failure_that_still_prints_the_text():
    ok, missing = negative.evaluate(0, "Result: passed\n", False, ["Result: passed"])
    assert ok and missing == []

    ok, _missing = negative.evaluate(1, "Result: passed\n", False, ["Result: passed"])
    assert not ok

    ok, missing = negative.evaluate(0, "nope\n", False, ["Result: passed"])
    assert not ok
    assert missing == ["Result: passed"]


def test_ansi_codes_do_not_hide_the_error_text():
    output = "\x1b[31m\x1b[1mname is required\x1b[0m\n"
    ok, missing = negative.evaluate(1, output, True, ["name is required"])
    assert ok and missing == []


def test_runner_keeps_the_production_lint_flags():
    script = (ROOT / "scripts" / "skills-lint.sh").read_text()
    for flag in negative.VALIDATOR_ARGS[1:]:
        assert flag in script
