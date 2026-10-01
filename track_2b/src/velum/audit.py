"""Second reader: what in the anonymised text could still identify a private party.

The audit reports risks for a human reviewer. It never looks anything up and never tries to name
anyone; it only points at passages of the output.
"""

import re

from .anonymize import PERSON, PLACE
from .detect import LANGUAGES, chunks, pattern_mentions, surface_regex
from .llm import chat_list

DECISION_CUE = re.compile(
    r"(?i)urteil|entscheid|beschluss|verfügung|verfahren|geschäft|prozess|arrêt|jugement|décision|"
    r"ordonnance|cause|procédure|sentenza|decisione|decreto|incarto|procedimento"
)
CASE_NUMBER = re.compile(
    r"\b(?:[A-Z]{1,5}[./ -]?\d{2,4}[./ -]\d{1,6}(?:[./-][A-Z0-9]{1,4})?|[A-Z]{2,}\d{4,}(?:[-/][A-Z0-9]{1,4})*|"
    r"[A-Z]{1,5}/\d{1,6}/\d{4}|\d{2}\.\d{4}\.\d{1,5})\b"
)
FEDERAL_CASE = re.compile(
    r"\b\d{1,2}[A-Z]{1,2}_\d+/\d{4}\b|\b[A-F]-\d+/\d{4}\b|\bBGE\b|\bSR\b|\bArt\b"
)
STOP = {
    "AG",
    "SA",
    "GmbH",
    "Sagl",
    "Holding",
    "Immobilien",
    "Treuhand",
    "Bau",
    "Transport",
    "Garage",
}

SCHEMA = {
    "type": "object",
    "properties": {
        "risks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "quote": {"type": "string"},
                    "reason": {"type": "string"},
                    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                },
                "required": ["quote", "reason", "severity"],
            },
        }
    },
    "required": ["risks"],
}
SYSTEM = (
    "You review anonymised Swiss court decisions before publication. You point out passages that "
    "could still let a neighbour, colleague or relative recognise a private party. You never guess "
    "who the parties are."
)
PROMPT = """Decision language: {language}. Placeholders such as A.________ and […] are already anonymised.

Quote up to 8 short passages from the excerpt that could still reveal who a private party is, for example:
a name or nickname left in clear, an address, a small place combined with dates, an employer combined with a job,
a vehicle or parcel number, an unusual event, or a lower-court case number that leads to a less anonymised file.
Placeholders are safe; never quote a placeholder on its own. Names of judges, clerks, lawyers, courts and authorities
are published on purpose; do not quote them, nor dates of the proceedings.{published}
For each passage give the exact quote, a one-sentence reason in English, and a severity (low, medium, high).
Return an empty list if nothing remains.

Excerpt:
<<<
{text}
>>>"""


def deterministic(output, entities):
    """Checks that need no model: leftover name parts, identifiers, case numbers, kept quasi-identifiers."""
    risks = []
    kept_tokens = {
        t.casefold()
        for e in entities
        if e.action == "keep"
        for n in e.names
        for t in n.split()
    }
    for e in entities:
        if e.action != "pseudonymize" or e.type not in PERSON | PLACE | {
            "private_company"
        }:
            continue
        tokens = {t.strip(",.") for n in e.names for t in n.split()}
        for tok in sorted(tokens):
            if (
                len(tok) < 3
                or not tok[0].isupper()
                or tok in STOP
                or tok.casefold() in kept_tokens
            ):
                continue
            for m in surface_regex(tok, r"(?:s|’s|'s)?").finditer(output):
                risks.append(
                    _risk(
                        output,
                        m.start(),
                        m.end(),
                        "high" if e.type != "private_company" else "medium",
                        f"part of the name behind {e.label} is still in the text",
                        "leftover",
                    )
                )
    kept_names = {n.casefold() for e in entities if e.action == "keep" for n in e.names}
    for m in pattern_mentions(output):
        if m.text.casefold() in kept_names:
            continue  # an authority's address, kept under the pack
        for hit in surface_regex(m.text).finditer(output):
            risks.append(
                _risk(
                    output,
                    hit.start(),
                    hit.end(),
                    "high",
                    f"{m.type.replace('_', ' ')} still in the text",
                    "pattern",
                )
            )
    for m in CASE_NUMBER.finditer(output):
        if FEDERAL_CASE.search(m.group(0)) or not DECISION_CUE.search(
            output, max(0, m.start() - 80), m.start()
        ):
            continue
        risks.append(
            _risk(
                output,
                m.start(),
                m.end(),
                "medium",
                "lower-instance case number: links this decision to the cantonal file",
                "cross-instance",
            )
        )
    for e in entities:
        if e.action == "keep" and e.type in {
            "occupation",
            "birth_date",
            "parcel_number",
        }:
            for name in set(e.names):
                for m in surface_regex(name).finditer(output):
                    risks.append(
                        _risk(
                            output,
                            m.start(),
                            m.end(),
                            "low",
                            f"{e.type.replace('_', ' ')} kept under {e.basis}; check it together with places and dates",
                            "quasi-identifier",
                        )
                    )
    return dedupe(risks)


def second_reader(output, language, published=(), size=6000):
    """Apertus reads the anonymised text the way a curious acquaintance would."""
    risks, usage_total = (
        [],
        {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "seconds": 0.0},
    )
    for start, end in chunks(output, size):
        part = output[start:end]
        items, usage = chat_list(
            SYSTEM,
            PROMPT.format(
                language=LANGUAGES.get(language, language),
                published=f" Published on purpose in this decision: {', '.join(published)}." if published else "",
                text=part,
            ),
            SCHEMA,
            max_tokens=2000,
        )
        usage_total["calls"] += 1
        for k in ("prompt_tokens", "completion_tokens", "seconds"):
            usage_total[k] += usage.get(k) or 0
        for r in items:
            hit = (
                surface_regex(r["quote"].strip()).search(part)
                if r["quote"].strip()
                else None
            )
            if hit:
                risks.append(
                    _risk(
                        output,
                        start + hit.start(),
                        start + hit.end(),
                        r["severity"],
                        r["reason"],
                        "apertus",
                    )
                )
    return dedupe(risks), usage_total


def _risk(text, start, end, severity, reason, source):
    return {
        "start": start,
        "end": end,
        "quote": text[start:end],
        "severity": severity,
        "reason": reason,
        "source": source,
    }


PLACEHOLDER = re.compile(r"\b[A-Z]{1,2}\.(?:_{2,})?|\[…\]|\[\.\.\.\]")
DATE_OR_AMOUNT = re.compile(
    r"\b\d{1,2}\.?\s*[^\W\d_]+\.?\s+\d{4}\b|\b\d{1,2}\.\d{1,2}\.\d{2,4}\b|"
    r"(?i:\b(?:fr|chf)\.?\s*)[\d'’.,]+(?:\.[-–]{1,2})?"
)
TITLE_WORD = re.compile(
    r"(?i)\b(?:rechtsanw\w*|fürsprech\w*|advokat\w*|avocat\w*|avvocat\w*|avv|dr|prof|me|maître|vertreten|"
    r"représenté\w*|patrocinat\w*)\b\.?"
)
OPEN_TO_ALL = {"court_official", "lawyer", "expert", "authority", "public_body", "authority_address"}


def published(entities):
    """Names the pack keeps for people and bodies; the second reader is told not to flag them."""
    return sorted({n for e in entities if e.action == "keep" and e.type in OPEN_TO_ALL for n in e.names}, key=len, reverse=True)


def screen(risks, entities):
    """Keep a second-reader quote only if something in it is not a placeholder, a kept name, a title, a date or an amount."""
    names = sorted({n for e in entities if e.action == "keep" for n in e.names}, key=len, reverse=True)
    words_kept = {t.casefold() for n in names for t in re.findall(r"[^\W\d_]{3,}", n)}
    shown = []
    for r in risks:
        rest = PLACEHOLDER.sub(" ", r["quote"])
        for name in names:
            rest = re.sub(re.escape(name), " ", rest, flags=re.I)
        rest = TITLE_WORD.sub(" ", DATE_OR_AMOUNT.sub(" ", rest))
        words = [w for w in re.findall(r"(?<!\w)[A-ZÀ-ÖØ-Þ][^\W\d_]{2,}", rest) if w.casefold() not in words_kept]
        if words or re.search(r"\d", rest):
            shown.append(r)
    return shown


def dedupe(risks):
    seen, out = set(), []
    for r in sorted(risks, key=lambda r: (r["start"], -r["end"])):
        if (r["start"], r["end"]) not in seen:
            seen.add((r["start"], r["end"]))
            out.append(r)
    return out
