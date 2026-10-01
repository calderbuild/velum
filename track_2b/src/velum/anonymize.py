"""Turn mentions into edits. Every edit is placed by code at a verified position and carries the
rule-pack article that requires it; text outside the edits is guaranteed unchanged."""

import re
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .detect import surface_regex

PACKS = Path(__file__).parent / "packs"
PERSON = {"private_person", "lawyer", "court_official", "expert"}
PLACE = {"residence", "place"}
AUTHORITY = {"authority", "public_body"}
ACTION_RANK = {"remove": 2, "pseudonymize": 2, "keep": 0}
LEGAL_FORM = re.compile(
    r"(?:\s*,)?\s+(?:AG|SA|GmbH|Sàrl|Sagl|S\.à\s?r\.l\.|S\.r\.l\.|Srl|S\.A\.|Ltd\.?|Inc\.|SE|KG|LLC|"
    r"in Liquidation|en liquidation|in liquidazione)$"
)
GENITIVE = r"(?:s|’s|'s)?"
BIRTH_CUE = re.compile(
    r"(?i)geb(?:oren|\.)|jahrgang|né[e]?\b|naissance|nat[oa]\b|nascita|born"
)
SOCIAL_INSURANCE = re.compile(
    r"(?i)sozialversicherung|(?:invaliden|unfall|kranken|arbeitslosen|militär)versicherung|berufliche Vorsorge|"
    r"ergänzungsleistung|soziale Sicherheit|IV-Stelle|SUVA|assurances? sociales?|"
    r"assurance-(?:invalidité|accidents|maladie|chômage)|prévoyance professionnelle|prestations complémentaires|"
    r"sécurité sociale|office AI|assicurazion[ei] social[ei]|assicurazione (?:invalidità|contro gli infortuni|malattia|"
    r"contro la disoccupazione)|previdenza professionale|prestazioni complementari|sicurezza sociale|Ufficio AI"
)


def load_pack(pack_id):
    return tomllib.loads((PACKS / f"{pack_id}.toml").read_text())


def available_packs():
    return sorted(p.stem for p in PACKS.glob("*.toml"))


def is_social_insurance(text, legal_area=""):
    return bool(
        SOCIAL_INSURANCE.search(legal_area or "")
        or SOCIAL_INSURANCE.search(text[:4000])
    )


@dataclass
class Entity:
    type: str
    names: list
    roles: list = field(default_factory=list)
    votes: Counter = field(default_factory=Counter)
    action: str = "keep"
    basis: str = ""
    why: str = ""
    label: str = ""  # placeholder or removal marker; empty when kept
    first: int = 0
    count: int = 0


def rule(pack, type_, social_insurance):
    cat = pack["category"][type_]
    if social_insurance and "social_insurance_action" in cat:
        return cat["social_insurance_action"], cat["social_insurance_basis"], cat["why"]
    return cat["action"], cat["basis"], cat["why"]


def decide(text, mentions, pack, social_insurance=False):
    """Group mentions into entities, apply the pack, return (entities, edits)."""

    def protective(counter):
        return max(
            counter,
            key=lambda t: (ACTION_RANK[rule(pack, t, social_insurance)[0]], counter[t]),
        )

    entities = _group(mentions, protective)
    for e in entities:
        e.action, e.basis, e.why = rule(pack, e.type, social_insurance)
    for e in _authority_addresses(text, entities):
        e.type = "authority_address"
        e.action, e.basis, e.why = rule(pack, e.type, social_insurance)
    spans = _occurrences(text, entities)
    edits = _non_overlapping(
        [s for s in spans if entities[s["entity"]].action != "keep"]
    )
    _label(entities, edits, pack)
    return entities, edits


def _surface_types(mentions, protective):
    votes, roles, forms = {}, {}, {}
    for m in mentions:
        key = m.text.casefold()
        votes.setdefault(key, Counter())[m.type] += 1
        roles.setdefault(key, set()).add(m.role)
        forms.setdefault(key, m.text)
    types = {}
    for key, counter in votes.items():
        if set(counter) <= PLACE or set(counter) & {"address", "identifier"}:
            types[key] = protective(
                counter
            )  # one statement of residence settles every occurrence
        else:
            best = max(counter.values())
            types[key] = protective(
                Counter({t: n for t, n in counter.items() if n == best})
            )
    return types, votes, roles, forms


def _group(mentions, protective):
    types, votes, roles, forms = _surface_types(mentions, protective)
    entities, by_token = [], {}
    # Longest names first, so "Hans Brunner" exists before "Brunner" looks for its entity.
    for key in sorted(types, key=lambda k: (-len(k.split()), -len(k))):
        t, name = types[key], forms[key]
        if t in PERSON:
            tokens = set(key.split())
            homes = [
                e for e in by_token.get(key.split()[-1], []) if tokens <= _tokens(e)
            ]
            if homes:
                homes[0].names.append(name)
                homes[0].roles += sorted(roles[key] - {""})
                homes[0].votes.update(votes[key])
                continue
        if t == "private_company":
            name = LEGAL_FORM.sub("", name).strip() or name
            if any(
                e.type == t and name.casefold() in _casefolded(e.names)
                for e in entities
            ):
                continue
        e = Entity(t, [name], sorted(roles[key] - {""}), Counter(votes[key]))
        entities.append(e)
        if t in PERSON:
            for tok in key.split():
                by_token.setdefault(tok, []).append(e)
    for e in entities:
        if e.type in PERSON:
            e.type = protective(
                Counter({t: n for t, n in e.votes.items() if t in PERSON})
            )
    for e in entities:
        if e.type in PERSON - {"court_official"}:
            _add_name_variants(e, entities)
    return entities


def _tokens(e):
    return {tok.casefold() for n in e.names for tok in n.split()}


def _casefolded(names):
    return {n.casefold() for n in names}


def _add_name_variants(e, entities):
    """Surname alone and initial + surname, unless another person shares the surname."""
    full = max(e.names, key=len).split()
    if len(full) < 2:
        return
    surname = full[-1]
    others = set().union(
        *(_tokens(o) for o in entities if o is not e and o.type in PERSON)
    )
    if len(surname) >= 3 and surname.casefold() not in others:
        e.names += [surname, f"{full[0][0]}. {surname}"]


def _find(text, e):
    for name in sorted(set(e.names), key=len, reverse=True):
        for m in surface_regex(name, GENITIVE if e.type in PERSON else "").finditer(
            text
        ):
            if e.type == "birth_date" and not BIRTH_CUE.search(
                text, max(0, m.start() - 40), m.end() + 40
            ):
                continue
            yield m.start(), m.end()


def _authority_addresses(text, entities):
    """Addresses whose nearest preceding name is a body the pack names in clear (Art. 7 Abs. 3).

    A body the pack anonymises, such as a municipality that is a party under the Zurich rules,
    keeps nothing: its address would give it away."""
    named = sorted(((end, e) for e in entities if e.type != "address" for _, end in _find(text, e)), key=lambda p: p[0])
    for e in entities:
        if e.type != "address":
            continue
        owners = []
        for s, _ in _find(text, e):
            before = [o for end, o in named if end <= s and s - end <= 150 and "\n\n" not in text[end:s]]
            owners.append(before[-1] if before else None)
        if owners and all(o and o.type in AUTHORITY and o.action == "keep" for o in owners):
            yield e


def _occurrences(text, entities):
    spans = []
    for i, e in enumerate(entities):
        found = [{"start": s, "end": t, "entity": i} for s, t in _find(text, e)]
        e.first = min((s["start"] for s in found), default=len(text))
        e.count = len(found)
        spans += found
    return spans


def _non_overlapping(spans):
    """Longest span wins. Kept spans never reach this point, so they never block an edit."""
    chosen = []
    for s in sorted(spans, key=lambda s: (-(s["end"] - s["start"]), s["start"])):
        if all(s["end"] <= c["start"] or s["start"] >= c["end"] for c in chosen):
            chosen.append(s)
    return sorted(chosen, key=lambda s: s["start"])


def _label(entities, edits, pack):
    edited = {s["entity"] for s in edits}
    used = [
        e for i, e in enumerate(entities) if e.action == "pseudonymize" and i in edited
    ]
    people = _letters(pack["person_letters"], "")
    places = _letters(pack["place_letters"], pack["person_letters"])
    for e in sorted(used, key=lambda e: e.first):
        e.label = pack["placeholder"].format(
            letter=next(places if e.type in PLACE else people)
        )
    for e in entities:
        if e.action == "remove":
            e.label = pack["removed"]


def _letters(first, avoid):
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    yield from first
    yield from (c for c in alphabet if c not in first + avoid)
    yield from (a + b for a in alphabet for b in alphabet)


def apply(text, entities, edits):
    """Write the edits into the text. Returns (output, log)."""
    out, log, pos = [], [], 0
    for s in edits:
        e = entities[s["entity"]]
        label = e.label
        if label.endswith(".") and text.startswith(".", s["end"]):
            label = label[:-1]  # "B." before a full stop, not "B.."
        out += [text[pos : s["start"]], label]
        log.append(
            {
                "start": s["start"],
                "end": s["end"],
                "original": text[s["start"] : s["end"]],
                "replacement": label,
                "entity": s["entity"],
                "type": e.type,
                "action": e.action,
                "basis": e.basis,
            }
        )
        pos = s["end"]
    out.append(text[pos:])
    output = "".join(out)
    verify_untouched(text, output, log)
    return output, log


def verify_untouched(original, output, log):
    """Diff guard: outside the logged edits, the output equals the original byte for byte."""
    o = p = 0
    for item in log:
        kept = original[o : item["start"]]
        if output[p : p + len(kept)] != kept:
            raise AssertionError(f"text changed before the edit at {item['start']}")
        p += len(kept)
        if output[p : p + len(item["replacement"])] != item["replacement"]:
            raise AssertionError(f"unexpected replacement at {item['start']}")
        p += len(item["replacement"])
        o = item["end"]
    if output[p:] != original[o:]:
        raise AssertionError("text changed after the last edit")


def kept_spans(text, entities, edits):
    """Where kept names occur outside every edit, so a reviewer sees what was left on purpose."""
    spans = []
    for i, e in enumerate(entities):
        if e.action != "keep":
            continue
        for s, t in _find(text, e):
            if all(t <= x["start"] or s >= x["end"] for x in edits + spans):
                spans.append({"start": s, "end": t, "entity": i})
    return sorted(spans, key=lambda s: s["start"])


def summary(entities, edits, kept):
    seen = Counter(s["entity"] for s in edits + kept)
    return [
        {
            "id": i,
            "label": e.label,
            "type": e.type,
            "action": e.action,
            "basis": e.basis,
            "why": e.why,
            "count": seen[i],
            "names": sorted(set(e.names), key=len, reverse=True),
            "roles": e.roles[:3],
        }
        for i, e in sorted(enumerate(entities), key=lambda p: p[1].first)
        if seen[i]
    ]
