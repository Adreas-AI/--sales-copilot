"""Checks every draft before a person sees it.

Errors mean the text is not fit to send (AI output with errors is replaced by the
template). Warnings are shown to the reviewer alongside the draft.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_WORDS = 180
MAX_SUBJECT_CHARS = 80

BANNED_PHRASES = (
    "i hope this email finds you well",
    "hope you're doing well",
    "hope you are doing well",
    "i wanted to reach out",
    "just wanted to reach out",
    "touch base",
    "circle back",
    "don't hesitate",
    "do not hesitate",
    "revolutionize",
    "revolutionise",
    "game-changer",
    "game changer",
    "cutting-edge",
    "supercharge",
    "synergy",
    "unlock the power",
    "take your business to the next level",
    "in today's fast-paced",
    "elevate your",
    "delve",
    "seamlessly",
)

PLACEHOLDER = re.compile(r"\[[A-Za-z][^\]\n]{0,40}\]|\{\{.*?\}\}|<[A-Z_ ]{3,}>|\bXX+\b")
AI_SELF_REFERENCE = re.compile(r"\b(as an ai|language model|i'?m an ai)\b", re.IGNORECASE)
# Claims that must be traceable to the context: percentages, money, multipliers.
CLAIM = re.compile(r"\d+(?:\.\d+)?\s?%|[$€£]\s?\d[\d,.]*|\b\d+(?:\.\d+)?x\b|\b\d+ percent\b", re.I)


@dataclass(frozen=True)
class Issue:
    code: str
    severity: str  # "error" | "warning"
    message: str

    def __str__(self) -> str:
        return f"{self.severity}:{self.code}: {self.message}"


def _norm_claim(value: str) -> str:
    return re.sub(r"\s+", "", value.lower())


def check(subject: str, body: str, *, facts_text: str) -> list[Issue]:
    issues: list[Issue] = []
    text = f"{subject}\n{body}"
    lowered = text.lower()

    if not subject.strip():
        issues.append(Issue("empty_subject", "error", "Subject is empty"))
    if not body.strip():
        issues.append(Issue("empty_body", "error", "Body is empty"))
    if len(subject) > MAX_SUBJECT_CHARS:
        issues.append(Issue("long_subject", "warning", f"Subject over {MAX_SUBJECT_CHARS} chars"))

    words = len(body.split())
    if words > MAX_WORDS:
        issues.append(Issue("too_long", "error", f"{words} words (max {MAX_WORDS})"))

    if m := PLACEHOLDER.search(text):
        issues.append(Issue("placeholder", "error", f"Unfilled placeholder {m.group(0)!r}"))
    if AI_SELF_REFERENCE.search(text):
        issues.append(Issue("ai_self_reference", "error", "Mentions being an AI"))

    known_claims = {_norm_claim(c) for c in CLAIM.findall(facts_text)}
    for claim in CLAIM.findall(text):
        if _norm_claim(claim) not in known_claims:
            issues.append(
                Issue(
                    "unsupported_claim", "error", f"{claim!r} does not appear in the source facts"
                )
            )

    for phrase in BANNED_PHRASES:
        if phrase in lowered:
            issues.append(Issue("cliche", "warning", f"Generic phrase: {phrase!r}"))
    if text.count("!") > 1:
        issues.append(Issue("exclamations", "warning", "More than one exclamation mark"))
    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(i.severity == "error" for i in issues)
