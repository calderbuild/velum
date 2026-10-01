"""Command line: python -m velum {anonymize,demo,bench,build,serve}."""

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import anonymize_document, bench, redact
from .anonymize import available_packs, is_social_insurance, load_pack
from .audit import deterministic, published, screen, second_reader
from .detect import apertus_mentions, apertus_sweep, pattern_mentions
from .llm import LLMError, config

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def cmd_anonymize(args):
    path = Path(args.file)
    case = (
        json.loads(path.read_text())
        if path.suffix == ".json"
        else {"text": path.read_text()}
    )
    result = anonymize_document(
        case["text"],
        args.language or case.get("language", ""),
        args.pack,
        case.get("legal_area", ""),
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{path.stem}.anonymized.txt").write_text(result["text"])
    (out / f"{path.stem}.velum.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1)
    )
    print_result(path.stem, result)
    print(f"\nwrote {out / (path.stem + '.anonymized.txt')} and {path.stem}.velum.json")


def cmd_demo(args):
    model, base, _ = config()
    print(f"Velum demo · model {model} · endpoint {base}\n")
    cases = [
        json.loads(line)
        for line in (DATA / "demo" / "cases.jsonl").read_text().splitlines()
    ]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    scores = []
    for case in cases:
        started = time.time()
        result = anonymize_document(
            case["text"], case["language"], args.pack, case["legal_area"]
        )
        s = bench.score(case, result["text"], result["edits"])
        scores.append(s)
        result |= {k: case[k] for k in ("id", "docket", "court", "decision_date", "source_url")}
        result |= {"score": s, "score_pack": args.pack}
        (out / f"{case['id']}.anonymized.txt").write_text(result["text"])
        (out / f"{case['id']}.velum.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=1)
        )
        print_result(
            f"{case['docket']} ({case['court']}, {case['language']}, {time.time() - started:.0f} s)",
            result,
        )
        print(
            f"  against gold: {s['gold'] - s['leaked']}/{s['gold']} identities removed, "
            f"{s['keep'] - s['keep_redacted']}/{s['keep']} judge/clerk/lawyer mentions kept\n"
        )
    agg = bench.aggregate(scores)
    print(
        f"Demo total: recall {agg['recall']:.1%} · zero-leak decisions {agg['zero_leak_cases']:.0%} · "
        f"over-redaction {agg['over_redaction']:.1%} · outputs in {out}/"
    )


def print_result(title, result):
    print(f"== {title} · rule pack {result['pack']}")
    for e in result["entities"]:
        shown = e["label"] or "kept"
        print(
            f"  {shown:<14} {e['type']:<16} {e['action']:<12} {e['basis']:<22} {e['names'][0][:40]} (x{e['count']})"
        )
    for r in result["risks"]:
        print(f"  ! {r['severity']:<6} {r['quote'][:50]!r}: {r['reason'][:90]}")
    u = result["usage"]["extraction"]
    print(
        f"  Apertus: {u['calls']} extraction call(s), {u['prompt_tokens']}+{u['completion_tokens']} tokens, "
        f"{len(result['usage']['rejected_mentions'])} mention(s) rejected as not in the text"
    )


# --- benchmark -------------------------------------------------------------------------------


def system_patterns(case, pack):
    return pattern_mentions(case["text"]), {}


def system_apertus(case, pack):
    found, usage = apertus_mentions(case["text"], case["language"])
    return pattern_mentions(case["text"]) + found, usage


SYSTEMS = {"velum": system_apertus, "patterns": system_patterns}


def run_rewrite(case, *_):
    """Baseline: the model rewrites the text; scored on the same gold as Velum."""
    from .rewrite import rewrite

    output, edits, usage = rewrite(case["text"], case["language"])
    s = bench.score(case, output, edits)
    s["leaks_flagged"] = 0
    return {
        "id": case["id"],
        "language": case["language"],
        "court": case["court"],
        "output": output,
        "edits": edits,
        "risks": [],
        "score": s,
        "usage": usage,
    }


def run_case(case, system, pack, sweep, reader):
    text = case["text"]
    social = is_social_insurance(text, case["legal_area"])
    mentions, usage = SYSTEMS[system](case, pack)
    entities, output, log = redact(text, mentions, pack, social)
    before = None
    if sweep:
        before = bench.score(case, output, log)
        missed, usage["sweep"] = apertus_sweep(
            text, output, case["language"], mentions, entities
        )
        usage["sweep"]["added"] = [m.text for m in missed]
        entities, output, log = redact(text, mentions + missed, pack, social)
    risks = deterministic(output, entities)
    if reader:
        extra, usage["second_reader"] = second_reader(
            output, case["language"], published(entities)
        )
        risks += screen(extra, entities)
    s = bench.score(case, output, log)
    s["leaks_flagged"] = flagged_leaks(case, log, risks)
    return {
        "id": case["id"],
        "language": case["language"],
        "court": case["court"],
        "output": output,
        "edits": log,
        "risks": risks,
        "score": s,
        "score_before_sweep": before,
        "usage": {k: v for k, v in usage.items() if k != "rejected"},
        "rejected": usage.get("rejected", []),
    }


def flagged_leaks(case, log, risks):
    """How many leaked gold mentions the audit pointed at (positions mapped into the output)."""

    def to_output(pos):
        return pos + sum(
            len(e["replacement"]) - (e["end"] - e["start"])
            for e in log
            if e["end"] <= pos
        )

    leaked = [g for g in case["gold"] if not bench._covered(g, log)]
    return sum(
        1
        for g in leaked
        if any(
            r["start"] < to_output(g["end"]) and r["end"] > to_output(g["start"])
            for r in risks
        )
    )


def cmd_bench(args):
    model = os.environ.get("LLM_NAME", "none") if args.system != "patterns" else "none"
    if args.system != "patterns":
        config()
    pack = load_pack(args.pack)
    cases = [
        json.loads(line)
        for line in (DATA / "velumbench" / f"{args.split}.jsonl")
        .read_text()
        .splitlines()
    ]
    if args.per_language:
        short = [c for c in cases if len(c["text"]) <= 15000]
        short.sort(key=lambda c: hashlib.sha256(c["id"].encode()).hexdigest())
        cases = [c for lang in ("de", "fr", "it") for c in [x for x in short if x["language"] == lang][: args.per_language]]
    cases = cases[: args.limit] if args.limit else cases
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sweep = args.sweep and args.system == "velum"
    reader = args.reader and args.system == "velum"
    tag = (
        f"{args.system}{'' if sweep or args.system != 'velum' else '-nosweep'}{'' if reader or args.system != 'velum' else '-noreader'}"
        f"_{model.split('/')[-1]}_{args.pack}_{args.split}"
    )
    path = out / f"{tag}.jsonl"
    done = (
        {json.loads(line)["id"] for line in path.read_text().splitlines()}
        if path.exists()
        else set()
    )
    todo = [c for c in cases if c["id"] not in done]
    print(
        f"{tag}: {len(cases)} cases, {len(done)} already done, running {len(todo)} with {args.workers} workers",
        file=sys.stderr,
    )
    with ThreadPoolExecutor(args.workers) as pool, path.open("a") as sink:
        run = run_rewrite if args.system == "rewrite" else run_case
        futures = {pool.submit(run, c, args.system, pack, sweep, reader): c for c in todo}
        for i, f in enumerate(as_completed(futures), 1):
            case = futures[f]
            try:
                row = f.result()
            except (LLMError, AssertionError) as e:
                row = {"id": case["id"], "language": case["language"], "error": str(e)}
            sink.write(json.dumps(row, ensure_ascii=False) + "\n")
            sink.flush()
            if i % 10 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}", file=sys.stderr)
    # a subset gets its own summary file, so it never overwrites the summary of the full split
    subset = (f".per-language-{args.per_language}" if args.per_language else "") + (
        f".limit-{args.limit}" if args.limit else ""
    )
    report(path, tag, cases, path.with_name(f"{path.stem}{subset}.summary.json"))


def _pass(usage, name):
    """Extraction counters sit at the top level of a bench row's usage; the other passes are nested."""
    return usage if name == "extraction" else usage.get(name) or {}


def report(path, tag, cases, summary_path):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    ids = {c["id"] for c in cases}
    rows = [r for r in rows if r["id"] in ids]
    ok = [r for r in rows if "error" not in r]
    summary = {
        "tag": tag,
        "cases": len(rows),
        "errors": len(rows) - len(ok),
        "all": bench.aggregate([r["score"] for r in ok]),
    }
    before = [r["score_before_sweep"] for r in ok if r.get("score_before_sweep")]
    if before:
        summary["before_sweep"] = bench.aggregate(before)
    for lang in ("de", "fr", "it"):
        summary[lang] = bench.aggregate(
            [r["score"] for r in ok if r["language"] == lang]
        )
    leaked = sum(r["score"]["leaked"] for r in ok)
    summary["leaks_flagged_by_audit"] = sum(
        r["score"]["leaks_flagged"] for r in ok
    ) / max(1, leaked)
    passes = ("extraction", "sweep", "second_reader")
    summary["usage"] = {
        p: {
            k: round(sum(_pass(r["usage"], p).get(k) or 0 for r in ok), 1)
            for k in ("calls", "prompt_tokens", "completion_tokens", "seconds")
        }
        for p in passes
    }
    summary["sweep_added"] = sum(
        len(r["usage"].get("sweep", {}).get("added", [])) for r in ok
    )
    summary["rejected_mentions"] = sum(len(r.get("rejected", [])) for r in ok)
    by_id = {c["id"]: c for c in cases}
    free = [(r, bench.free_form(by_id[r["id"]], r["edits"])) for r in ok]
    summary["free_form"] = {
        "edits": sum(len(f) for _, f in free),
        "decisions": sum(1 for _, f in free if f),
        "decisions_with_digits": sum(
            1
            for r, f in free
            if any(
                ch.isdigit()
                for e in f
                for ch in by_id[r["id"]]["text"][e["start"] : e["end"]] + e["replacement"]
            )
        ),
    }
    summary_path.write_text(json.dumps(summary, indent=1))
    a = summary["all"]
    print(f"\n{tag}  ({summary['cases']} cases, {summary['errors']} errors)")
    print(
        f"  recall {a['recall']:.2%}  zero-leak cases {a['zero_leak_cases']:.1%}  over-redaction {a['over_redaction']:.2%}  "
        f"consistency {a['consistency']:.1%}  extra chars/1k {a['extra_chars_per_1k']:.1f}"
    )
    if before:
        b = summary["before_sweep"]
        print(f"  before the sweep: recall {b['recall']:.2%}, over-redaction {b['over_redaction']:.2%}")
    print(
        f"  recall by kind: "
        + ", ".join(f"{k} {v:.1%}" for k, v in a["recall_by_kind"].items())
    )
    for lang in ("de", "fr", "it"):
        x = summary[lang]
        if not x["cases"]:
            continue
        print(
            f"  {lang}: recall {x['recall']:.2%}, over-redaction {x['over_redaction']:.2%}, cases {x['cases']}"
        )
    for p, u in summary["usage"].items():
        if u["calls"]:
            print(f"  {p}: {u['calls']:.0f} calls, {u['prompt_tokens']:.0f}+{u['completion_tokens']:.0f} tokens, {u['seconds']:.0f} s")
    print(
        f"  leaks flagged by audit {summary['leaks_flagged_by_audit']:.0%}, mentions rejected {summary['rejected_mentions']}, "
        f"names added by sweep {summary['sweep_added']}"
    )
    f = summary["free_form"]
    print(
        f"  free-form changes outside the names: {f['edits']} in {f['decisions']} decisions, "
        f"{f['decisions_with_digits']} of them touching digits"
    )


# --- building the benchmark and serving ------------------------------------------------------


def cmd_build(args):
    rows = [
        json.loads(line)
        for src in args.sources
        for line in Path(src).read_text().splitlines()
    ]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    splits = {"dev": [], "test": []}
    for row in rows:
        case = bench.generate(row)
        if case and case["gold"]:
            splits[bench.split_of(case["id"])].append(case)
    for name, cases in splits.items():
        (out / f"{name}.jsonl").write_text(
            "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases)
        )
        print(
            f"{name}: {len(cases)} cases, {sum(len(c['gold']) for c in cases)} gold mentions, "
            f"{sum(k['count'] for c in cases for k in c['keep'])} keep mentions"
        )


def cmd_serve(args):
    from .server import serve

    serve(args.host, args.port, args.results)


def main():
    p = argparse.ArgumentParser(prog="velum")
    sub = p.add_subparsers(dest="cmd", required=True)
    packs = available_packs()
    a = sub.add_parser(
        "anonymize", help="anonymise one decision (.txt or .json with a text field)"
    )
    a.add_argument("file")
    a.add_argument("--pack", default="bger-2020", choices=packs)
    a.add_argument("--language", default="", choices=["", "de", "fr", "it"])
    a.add_argument("--out", default="out")
    d = sub.add_parser(
        "demo", help="run the full pipeline on the bundled demo decisions"
    )
    d.add_argument("--pack", default="bger-2020", choices=packs)
    d.add_argument("--out", default="out/demo")
    b = sub.add_parser("bench", help="score a system on VelumBench")
    b.add_argument("--system", default="velum", choices=sorted(SYSTEMS) + ["rewrite"])
    b.add_argument("--split", default="test", choices=["dev", "test"])
    b.add_argument("--pack", default="bger-2020", choices=packs)
    b.add_argument("--limit", type=int, default=0)
    b.add_argument(
        "--per-language",
        type=int,
        default=0,
        help="a fixed sample: N decisions of up to 15k characters per language",
    )
    b.add_argument("--workers", type=int, default=8)
    b.add_argument(
        "--sweep",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="let Apertus reread the output for missed names",
    )
    b.add_argument(
        "--reader",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="run the Apertus second reader",
    )
    b.add_argument("--out", default="out/bench")
    g = sub.add_parser(
        "build", help="build VelumBench from published decisions (jsonl)"
    )
    g.add_argument("sources", nargs="+")
    g.add_argument("--out", default=str(DATA / "velumbench"))
    s = sub.add_parser("serve", help="review interface on http://localhost:PORT")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--host", default="127.0.0.1", help="0.0.0.0 inside a container")
    s.add_argument("--results", default="out/demo", help="folder with .velum.json files to open")
    args = p.parse_args()
    {
        "anonymize": cmd_anonymize,
        "demo": cmd_demo,
        "bench": cmd_bench,
        "build": cmd_build,
        "serve": cmd_serve,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
