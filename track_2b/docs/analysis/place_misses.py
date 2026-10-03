"""Where the places missed by Velum with Apertus 70B come from, and what a residence cue rule would add.

Run from track_2b/: python3 docs/analysis/place_misses.py
Reads the saved run in results/ and the hand labels in docs/analysis/place_misses_labels.tsv; no model call.
"""
import collections
import csv
import gzip
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "src")
from velum.bench import _covered  # noqa: E402

RUN = "results/velum_Apertus-v1.5-70B_bger-2020_test.jsonl.gz"
LABELS = Path(__file__).with_name("place_misses_labels.tsv")
CUE = (
    r"(?:wohnhaft in|Wohnsitz in|wohnt in|wohnte in|mit Sitz in|mit damaligem statutarischen Sitz in|Sitz in|"
    r"domiciliée? à|dont le siège (?:se situe|est) (?:à|en Ville de)|avec siège à|sise? à|"
    r"con sede a|sede effettiva a|domiciliat[oa] a|residente a)\s+"
)
NAME = r"((?:[A-ZÄÖÜÉÈ][\w'’-]+)(?:[ -](?:[A-ZÄÖÜÉÈ][\w'’-]+|de|di|am|an|bei))*)"
RESIDENCE_CUE = re.compile(CUE + NAME)

cases = {json.loads(line)["id"]: json.loads(line) for line in open("data/velumbench/test.jsonl")}
rows = [json.loads(line) for line in gzip.open(RUN, "rt")]


def missed_places():
    """(case id, entity, leaked mentions) in file order, the order the labels are numbered in."""
    for r in rows:
        case = cases[r["id"]]
        by_entity = collections.defaultdict(list)
        for g in case["gold"]:
            if g["kind"] == "place" and not _covered(g, r["edits"]):
                by_entity[g["entity"]].append(g)
        for entity, mentions in by_entity.items():
            yield r["id"], entity, mentions


def by_label():
    labels = {(row["case"], row["entity"]): row["label"] for row in csv.DictReader(open(LABELS), delimiter="\t")}
    entities, mentions, decisions = collections.Counter(), collections.Counter(), collections.defaultdict(set)
    for case_id, entity, ms in missed_places():
        label = labels[(case_id, entity)]
        entities[label] += 1
        mentions[label] += len(ms)
        decisions[label].add(case_id)
    assert sum(entities.values()) == len(labels), "labels and run disagree"
    for label in sorted(entities):
        print(f"{label}: {entities[label]} entities, {mentions[label]} mentions, {len(decisions[label])} decisions")


def residence_rule():
    """Replace every occurrence of a name that follows a residence or seat cue, on top of Velum's edits."""
    gold = leaked = recovered = extra = 0
    for r in rows:
        case, text = cases[r["id"]], cases[r["id"]]["text"]
        names = {m.group(1) for m in RESIDENCE_CUE.finditer(text)}
        added = [
            {"start": m.start(), "end": m.end()}
            for n in names
            for m in re.finditer(r"(?<!\w)" + re.escape(n) + r"(?!\w)", text)
        ]
        gold_chars = set().union(*(range(g["start"], g["end"]) for g in case["gold"]))
        edited = set().union(*(range(e["start"], e["end"]) for e in r["edits"]))
        extra += sum(
            1
            for a in added
            for i in range(a["start"], a["end"])
            if i not in gold_chars and i not in edited and text[i].isalnum()
        )
        for g in case["gold"]:
            gold += 1
            if not _covered(g, r["edits"]):
                leaked += 1
                recovered += _covered(g, r["edits"] + added)
    print(
        f"residence cue rule: {recovered} of {leaked} leaked mentions recovered, "
        f"recall {1 - leaked / gold:.2%} -> {1 - (leaked - recovered) / gold:.2%}, "
        f"{extra} letters and digits changed outside the gold"
    )


if __name__ == "__main__":
    by_label()
    residence_rule()
