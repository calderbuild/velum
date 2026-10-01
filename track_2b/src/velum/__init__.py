"""Velum: anonymisation of Swiss court decisions with Apertus, citable rule packs and a second reader."""

import os

from dataclasses import asdict

from .anonymize import apply, decide, is_social_insurance, kept_spans, load_pack, summary
from .audit import dedupe, deterministic, published, screen, second_reader
from .detect import Mention, apertus_mentions, apertus_sweep, pattern_mentions, surface_regex

STOPWORDS = {
    "de": {"der", "die", "und", "das", "nicht", "ist", "des", "den", "dem", "mit"},
    "fr": {"le", "la", "les", "des", "et", "est", "une", "pour", "que", "du"},
    "it": {"il", "che", "di", "non", "per", "una", "sono", "gli", "della", "del"},
}


def guess_language(text):
    words = text.lower().split()[:3000]
    return max(STOPWORDS, key=lambda lang: sum(w in STOPWORDS[lang] for w in words))


def redact(text, mentions, pack, social):
    """Decide per rule pack and write the edits; apply() checks that nothing else changed."""
    entities, edits = decide(text, mentions, pack, social)
    return (entities, *apply(text, entities, edits))


def anonymize_document(text, language="", pack_id="bger-2020", legal_area=""):
    """Full pipeline: detect, decide per rule pack, edit, sweep, edit again, audit."""
    language = language or guess_language(text)
    pack = load_pack(pack_id)
    social = is_social_insurance(text, legal_area)
    found, stats = apertus_mentions(text, language)
    mentions = pattern_mentions(text) + found
    entities, output, _ = redact(text, mentions, pack, social)
    missed, sweep = apertus_sweep(text, output, language, mentions, entities)
    mentions += missed
    entities, output, _ = redact(text, mentions, pack, social)
    reader, usage = second_reader(output, language, published(entities))
    result = review(text, language, legal_area, pack_id, mentions, reader)
    result["model"] = os.environ.get("LLM_NAME", "")
    result["usage"] = {
        "extraction": {k: v for k, v in stats.items() if k != "rejected"},
        "sweep": sweep | {"added": [m.text for m in missed]},
        "second_reader": usage,
        "rejected_mentions": stats["rejected"],
    }
    return result


def review(text, language, legal_area, pack_id, mentions, reader):
    """Everything that follows from the mentions. Switching the rule pack reruns only this, without Apertus."""
    pack = load_pack(pack_id)
    social = is_social_insurance(text, legal_area)
    entities, output, log = redact(text, mentions, pack, social)
    kept = kept_spans(text, entities, log)
    risks = deterministic(output, entities)
    for r in screen(reader, entities):
        hit = surface_regex(r["quote"]).search(output)
        if hit:
            risks.append(r | {"start": hit.start(), "end": hit.end()})
    risks = dedupe(risks)
    return {
        "pack": pack_id,
        "pack_title": pack["title"],
        "pack_source": pack["source"],
        "language": language,
        "legal_area": legal_area,
        "social_insurance": social,
        "original": text,
        "text": output,
        "edits": log,
        "kept": kept,
        "entities": summary(entities, log, kept),
        "risks": risks,
        "mentions": [asdict(m) for m in mentions],
        "reader": reader,
    }


def from_dicts(mentions):
    return [Mention(**m) for m in mentions]


__all__ = [
    "anonymize_document",
    "apply",
    "redact",
    "review",
    "from_dicts",
    "decide",
    "load_pack",
    "pattern_mentions",
    "surface_regex",
]
