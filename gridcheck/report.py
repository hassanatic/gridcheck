"""Markdown report: verdicts first, then the evidence and the studies behind them."""
from __future__ import annotations

from .checks import CheckResult
from .profiles import Profile


def _evidence(evidence: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in evidence.items()) or "-"


def to_markdown(results: list[CheckResult], profile: Profile, *, summary: str, summary_source: str,
                studies: dict | None = None, title: str = "Grid code compliance report") -> str:
    lines = [f"# {title}", "", f"**Profile:** {profile.name}", "", f"**Source:** {profile.source}", ""]
    if profile.note:
        lines += [f"> {profile.note}", ""]
    lines += ["## Summary", "", summary, "", f"*Summary written by: {summary_source}.*", "",
              "## Checks", "", "| Check | Requirement | Verdict | Evidence |", "|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r.check_id} | {r.requirement} | **{r.verdict}** | {_evidence(r.evidence)} |")

    noted = [r for r in results if r.notes]
    if noted:
        lines += ["", "## Notes", ""]
        lines += [f"- **{r.check_id}:** {' '.join(r.notes)}" for r in noted]

    problems = profile.frt.rfg_range_problems()
    lines += ["", "## Profile parameters against the RfG ranges", ""]
    lines += [f"- {p}" for p in problems] if problems else ["- All fault-ride-through parameters are inside the RfG ranges."]

    for name, rows in (studies or {}).items():
        lines += ["", f"## Study: {name}", ""]
        if rows:
            headers = list(rows[0])
            lines += ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
            lines += ["| " + " | ".join(str(row[h]) for h in headers) + " |" for row in rows]
    return "\n".join(lines) + "\n"
