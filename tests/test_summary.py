from gridcheck import FAIL, PASS, CheckResult
from gridcheck.summary import is_consistent, summarise

RESULTS = [
    CheckResult("frt_rides_through", "frt", PASS),
    CheckResult("frequency_low_trip", "freq", FAIL, notes=["Disconnected after 5.0 min."]),
]


def test_without_a_model_the_summary_comes_from_the_results():
    text, source = summarise(RESULTS)
    assert source == "rules"
    assert "1 failed" in text and "frequency_low_trip" in text


def test_a_consistent_model_draft_is_used():
    draft = "One issue: frequency_low_trip failed because the unit disconnected too early. The rest passed."
    text, source = summarise(RESULTS, complete=lambda prompt: draft)
    assert (text, source) == (draft, "model")


def test_a_draft_that_hides_a_failure_is_rejected():
    _, source = summarise(RESULTS, complete=lambda prompt: "The plant is fully compliant.")
    assert source == "rules"


def test_a_draft_that_claims_full_compliance_is_rejected_even_if_it_names_the_failure():
    assert not is_consistent("frequency_low_trip noted, but all checks passed.", RESULTS)


def test_a_model_error_falls_back_to_rules():
    def broken(prompt):
        raise TimeoutError("model unreachable")

    _, source = summarise(RESULTS, complete=broken)
    assert source == "rules"


def test_the_prompt_carries_the_verdicts():
    seen = {}

    def capture(prompt):
        seen["prompt"] = prompt
        return "frequency_low_trip failed."

    summarise(RESULTS, complete=capture)
    assert '"verdict": "FAIL"' in seen["prompt"] and "frequency_low_trip" in seen["prompt"]
