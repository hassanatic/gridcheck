"""Plain-language summary of a compliance run, optionally drafted by a language model.

The model only words the summary. The verdicts come from the checks. A draft that leaves out
a failed check, or claims full compliance when something failed, is thrown away and replaced
by a summary built from the results themselves.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from collections import Counter

from .checks import FAIL, NEEDS_JUSTIFICATION, NOT_APPLICABLE, PASS, CheckResult

_FULL_COMPLIANCE = re.compile(r"\b(fully compliant|all checks pass(ed)?|passes all|no issues)\b", re.I)


def rule_based_summary(results: list[CheckResult]) -> str:
    counts = Counter(r.verdict for r in results)
    parts = [f"{len(results)} checks: {counts[PASS]} passed, {counts[FAIL]} failed, "
             f"{counts[NEEDS_JUSTIFICATION]} need justification, {counts[NOT_APPLICABLE]} not applicable."]
    for r in results:
        if r.verdict in (FAIL, NEEDS_JUSTIFICATION):
            reason = r.notes[-1] if r.notes else r.requirement
            parts.append(f"{r.check_id} ({r.verdict}): {reason}")
    return " ".join(parts)


def is_consistent(draft: str, results: list[CheckResult]) -> bool:
    """A draft must name every failed check and must not claim full compliance if any failed."""
    failed = [r.check_id for r in results if r.verdict == FAIL]
    if any(check_id.lower() not in draft.lower() for check_id in failed):
        return False
    if failed and _FULL_COMPLIANCE.search(draft):
        return False
    return True


def build_prompt(results: list[CheckResult]) -> str:
    rows = [{"check_id": r.check_id, "verdict": r.verdict, "requirement": r.requirement,
             "evidence": r.evidence, "notes": r.notes} for r in results]
    return ("Summarise these grid code compliance check results for a project manager who is not "
            "a power systems engineer. Use at most 120 words. Name every check that FAILED by its "
            "check_id. Do not change any verdict and do not add facts.\n\n" + json.dumps(rows, indent=1))


def summarise(results: list[CheckResult], complete=None) -> tuple[str, str]:
    """Return (summary, source). source is "model" when the draft was used, otherwise "rules".

    complete is any function that takes a prompt string and returns text.
    """
    if complete is not None:
        try:
            draft = complete(build_prompt(results))
        except Exception:  # an unreachable model must never block the report
            draft = None
        if draft and is_consistent(draft, results):
            return draft.strip(), "model"
    return rule_based_summary(results), "rules"


def openai_compatible_client():
    """A complete() function for an OpenAI-compatible chat API, or None if it is not configured.

    Set GRIDCHECK_LLM_BASE_URL (for example https://api.openai.com/v1), GRIDCHECK_LLM_MODEL
    and GRIDCHECK_LLM_API_KEY.
    """
    base = os.environ.get("GRIDCHECK_LLM_BASE_URL")
    model = os.environ.get("GRIDCHECK_LLM_MODEL")
    key = os.environ.get("GRIDCHECK_LLM_API_KEY")
    if not (base and model and key):
        return None

    def complete(prompt: str) -> str:
        body = json.dumps({"model": model, "temperature": 0,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        request = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=body, headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)["choices"][0]["message"]["content"]

    return complete
