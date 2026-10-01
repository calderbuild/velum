"""Baseline for the report: Apertus rewrites the decision itself, the approach most people try first.

The rewritten text is aligned with the original character by character, so it is scored exactly
like Velum's edits, including every change it makes outside the names it was asked to replace."""

import difflib

from .detect import LANGUAGES, chunks
from .llm import chat_text

SYSTEM = "You anonymise Swiss court decisions for publication. You return the full text with only the required changes."
PROMPT = """Decision language: {language}.
Anonymise this excerpt of a Swiss court decision for publication, following the rules of the Federal Supreme Court:
- replace each private person and each private company by a placeholder A.________, B.________, C.________ and so on,
  the same placeholder for the same person every time; keep a legal form such as "AG" or "SA" after the placeholder;
- replace the place where a private party lives or has its seat by U.________, V.________ and so on;
- remove the street addresses of private parties, writing […] instead;
- keep the names of judges, court clerks, lawyers, courts, authorities and public bodies;
- change nothing else: same wording, same line breaks.
Reply with the anonymised excerpt only.

Excerpt:
<<<
{text}
>>>"""


def rewrite(text, language, size=6000):
    """Returns (output, edits, usage). Edits are the character differences to the original."""
    out, edits = [], []
    usage = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "seconds": 0.0, "cut_off": 0}
    for start, end in chunks(text, size):
        part = text[start:end]
        new, used, cut = chat_text(SYSTEM, PROMPT.format(language=LANGUAGES.get(language, language), text=part), 4096)
        new = new.strip().removeprefix("<<<").removesuffix(">>>").strip("\n")
        usage["calls"] += 1
        usage["cut_off"] += cut
        for k in ("prompt_tokens", "completion_tokens", "seconds"):
            usage[k] += used.get(k) or 0
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, part, new, autojunk=False).get_opcodes():
            if op != "equal":
                edits.append({"start": start + i1, "end": start + i2, "replacement": new[j1:j2]})
        out.append(new)
    return "".join(out), edits, usage
