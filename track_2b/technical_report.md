# Technical report: Velum

Anonymising Swiss court decisions with Apertus, with every edit tied to the rule that requires it.

- **Track:** Track 2B: Velum
- **Event:** Online
- **Team:** Calder: Calder Luo
- **Demo:** TBD_VIDEO
- **Code:** [github.com/calderbuild/velum](https://github.com/calderbuild/velum) · **Data:** TBD_HF

## 1. Summary

Swiss courts publish their decisions in anonymised form. For the Federal Supreme Court this is
Art. 27 para. 2 BGG, and in 2025 that court alone issued 7,883 judgments. Clerks anonymise by
hand under rules that are precise and differ between courts. Asked in 2017, cantonal courts put the
work at 46 minutes per decision on average, and at 48 minutes where software helped [8]. The Federal
Supreme Court names lawyers, judges and court-appointed experts, except experts in social-insurance
cases. The Zurich cantonal administration replaces all of them. The obvious LLM approach is to ask a
model to rewrite the decision, and it fails in two ways a court cannot accept: it misses names, and
it changes text nobody asked it to touch. In my baseline, Apertus 70B rewrote 60 decisions under the
federal rules. It removed 70.8% of the identities, and in 45 of the 60 outputs it also changed text
outside the names: 215 rewordings, deletions and altered numbers, among them a cited case number
and, in one decision, the first point of the operative part.

Velum splits the work between Apertus and code. Apertus finds and classifies mentions, and a
mention counts only if it occurs verbatim in the text. A rule pack, one TOML file per court, maps
each category to keep, replace or remove and to the article that says so. Code writes the edits,
and a diff guard proves that every other character is unchanged. Apertus then rereads the draft
twice: once for names nobody classified, once as a second reader looking for residual risks. A
review page shows the clerk each edit with its article. On VelumBench, an open test set of 537
held-out decisions in German, French and Italian built from published decisions, Velum with
Apertus 70B removed 89.4% of the identities (96.7% on the baseline's 60 decisions), kept 98.8%
of the names the courts publish, and changed nothing outside its logged edits. The same pipeline
runs with no network at all, against Apertus 8B in llama.cpp.

## 2. Architecture

![Velum pipeline: find, decide, write, sweep, audit, review](docs/architecture.svg)

1. **Find** (`src/velum/detect.py`). The decision is split at paragraph breaks into windows of
   about 6,000 characters. For each window Apertus returns `{mention, role, type}` items under a
   strict JSON schema with 14 types. Names found in earlier windows are passed on with their types,
   so a party keeps one type across the decision. Code then corrects the slips I saw on the dev split:
   a person whose role is "judge" becomes a court official; a chamber typed as a person becomes an
   authority; role nouns ("der Beschwerdeführer"), case numbers and citations are dropped. A mention
   is kept only if it occurs verbatim in the text. Regular expressions add structured identifiers:
   AHV numbers, IBANs, phone numbers, e-mail and street addresses, parcel numbers, licence plates.
2. **Decide** (`anonymize.py`, `packs/*.toml`). Mentions are grouped into entities; the surname
   alone and initial + surname are added as variants unless another person shares the surname. When
   the model typed the same name in different ways, the more protective action wins. The pack gives
   each entity an action, the article and a reason. An address whose owner is an authority the pack
   names stays (BGer Art. 7 para. 3).
3. **Write.** Code replaces every occurrence, longest span first, and assigns letters in order of
   first appearance: `A.________` for parties, `U.________` for places, `[…]` for removals.
   `verify_untouched` walks original and output together and raises if any character outside the
   logged edits differs.
4. **Sweep.** Apertus reads the anonymised draft and lists private names still in clear. A
   suggestion is accepted only if it occurs verbatim in the original, no earlier pass typed it, it is
   not part of a name the pack keeps, and the text never introduces it with a judge's, clerk's or
   lawyer's title. The sweep can add redactions; it cannot undo a decision of the pack.
5. **Audit** (`audit.py`). A second Apertus reader quotes up to 8 passages per window that could
   still identify a party. The names the pack keeps are passed in so it does not flag them, and code
   drops quotes that contain nothing but placeholders, published names, dates and amounts.
   Deterministic checks add leftover parts of replaced names, identifiers, lower-instance case
   numbers and quasi-identifiers the pack keeps (occupation, birth year, parcel number).
6. **Review** (`server.py`, `static/index.html`). A standard-library HTTP server and one HTML file
   with no external resources. The clerk sees the decision with each edit marked and its article in
   the margin, the names kept on purpose, and the risks. Switching the rule pack re-runs steps 2 and
   3 and the deterministic checks of step 5 on the stored mentions and second-reader quotes, without
   a model call; the page reports the time (18 ms for the decision in the demo video).

![The review page for decision 1C_92/2025 under the federal rules](docs/review.png)

*The review page (1C_92/2025, federal rules). Each replaced name is struck through next to its
placeholder, the margin gives the article, names kept on purpose are marked "stet", and the panel
explains the selected entity.*

**Target architecture: b) air-gapped.** Velum needs nothing beyond the Python standard library and
makes no network request except to `LLM_BASE_URL`. `compose.airgapped.yml` puts Velum and a
llama.cpp server with Apertus v1.5 8B (Q4_K_M) on a Docker network marked `internal`, which has no
route out, and `make airgapped` runs the demo there (`docs/airgapped.md`). The same image runs
**a) on-premise** against any OpenAI-compatible server in the court's network that serves Apertus.
The reported numbers come from the endpoint of the Swiss National Supercomputing Centre (CSCS),
which the hackathon provides; for real decisions a court would use a) or b).

| Dependency | Build time | Runtime |
| --- | --- | --- |
| Velum | `python:3.12-slim` image and this repository | the Apertus endpoint, nothing else |
| Air-gapped Apertus | llama.cpp image `server-b11312`, GGUF file (5.06 GB) | nothing |
| Review page | none | no fonts, scripts or images from outside |

## 3. Use of Apertus

- **Models:** `swiss-ai/Apertus-v1.5-70B` (main results, demo) and `swiss-ai/Apertus-v1.5-8B` on the
  CSCS endpoint; Apertus v1.5 8B as GGUF Q4_K_M in llama.cpp `b11312` for the air-gapped run.
- **How:** inference only, in three roles: extraction, sweep, second reader. No fine-tuning. No other
  model is used anywhere. VelumBench gold comes from the courts' own placeholders, so the
  evaluation needs no LLM judge.
- **Settings:** temperature 0, `chat_template_kwargs: {enable_thinking: false}`, and
  `response_format` with a strict JSON schema. The endpoint generates object properties in
  alphabetical order, so I named them to make that the order in which the model should work:
  `mention`, `role`, `type` (copy the name, say what the person does, then classify). `maxItems: 60`
  stops repetition loops. If a reply still hits `max_tokens`, Velum labels the two halves of the
  window separately, or keeps the complete items of the partial JSON.
- **Why Apertus:** decisions arrive in German, French and Italian, often mixed (court names, quoted
  lower-court rulings). Apertus is an open, multilingual Swiss model whose weights a court can run
  inside its own perimeter, which is what the court data requires.

## 4. Data

**VelumBench** (`data/README.md`) is built from 750 decisions sampled from
[`voilaj/swiss-caselaw`](https://huggingface.co/datasets/voilaj/swiss-caselaw) (CC0-1.0) at a pinned
revision: Federal Supreme Court, Federal Administrative Court, Federal Criminal Court and six cantonal
courts, with a fixed seed. Each placeholder the court wrote (`A.________`) is filled with an invented
Swiss identity, the same one for every occurrence of the letter, which gives realistic input with
exact gold spans. Names the courts publish on purpose (judges, clerks, lawyers) become the gold for
what must stay. A hash of the decision id sends one decision in seven to dev; I used only dev while
building and ran test once, on the final code. Dev has 79 decisions (1,459 gold mentions, 450
keep mentions). Test has 537 decisions (de 198, fr 180, it 159), 8,390 gold mentions of 2,471
entities, and 3,168 mentions of 2,072 published names that must stay.

**Licence.** Decision texts are official decisions and are not protected by copyright (Art. 5 para. 1
let. c URG). The invented identities, annotations and splits are CDLA-Permissive-2.0.

**Personal data.** No real party is re-identified: every inserted person, company and place is
invented, and none of its words occurs in the source decision. Judges, clerks and lawyers appear as
the courts published them. No human subjects were involved.

**Rule packs.** `bger-2020` encodes the Federal Supreme Court's "Regeln für die Anonymisierung der
Urteile" (2020); `zh-entscheide-2025` encodes the Zurich «ZHEntscheide» guide (March 2025). Both are
public documents; each category cites its article and each pack links its source.

## 5. Evaluation

**Task.** Input: a decision with invented identities in place of the court's placeholders, its
language and legal area. Output: the anonymised text and the edit log. All systems are scored with
the BGer 2020 pack on the same gold (`src/velum/bench.py`):

- **Recall:** share of gold mentions whose letters and digits are all covered by edits.
- **Zero-leak:** share of decisions with nothing leaked.
- **Over-redaction:** share of mentions of published judges, clerks and lawyers missing from the output.
- **Consistency:** share of entities mentioned more than once that received a single placeholder.
- **Extra:** letters and digits changed outside gold spans per 1,000 characters (this includes
  identifiers and addresses the pack correctly removes).

**Runs.** One run per system on the test split, on the final code, on 1 October 2026, with the
CSCS endpoint at temperature 0. The raw outputs and summaries are in `results/`; every summary
recomputes from its raw output without a model call.

**Against the rewrite baseline.** A whole-text rewrite of a long decision does not fit into one
reply, so this comparison uses the 293 test decisions of at most 15,000 characters and takes the
first 20 per language in hash order.

| Same 60 decisions | Recall | Zero-leak | Over-redaction | Consistency | Changes outside the names | Tokens per decision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Rewrite, Apertus 70B | 70.8% | 13.3% | 4.3% | 88.2% | 215 in 45 decisions | 4,600 |
| Velum, Apertus 70B | **96.7%** | **81.7%** | **2.8%** | **96.8%** | **0** | 10,400 |

Changes outside the names are edits outside the gold spans that write anything other than a
placeholder or a removal marker: rewordings, deleted passages, changed numbers. In 13 of the 45
decisions such a change involves digits, as with the cited case number in section 1. Velum spends
about twice the tokens of the rewrite on these decisions.

**All 537 decisions.**

| All 537 decisions | Recall | Zero-leak | Over-redaction | Consistency | Extra per 1k | Tokens per decision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Patterns only, no model | 4.6% | 0.0% | 0.0% | n/a | 1.6 | 0 |
| Velum, Apertus 8B | 76.4% | 49.5% | 0.5% | 97.5% | 5.0 | 21,800 |
| Velum, Apertus 70B | **89.4%** | **64.4%** | 1.2% | 93.5% | 8.2 | 22,500 |

- **By kind** (70B / 8B): addresses 99.5% / 98.9%, companies 97.3% / 84.4%, persons 90.0% / 77.2%,
  places 46.0% / 13.6%. By language (70B): German 86.4%, French 92.4%, Italian 88.2%. By court
  (70B): from 73.7% (Zurich Obergericht, 24 decisions) to 96.1% (Vaud, 23); Federal Supreme Court
  93.5% (356).
- **Where the misses are.** Of the 892 gold mentions the 70B run missed, 674 are persons (76%) and
  190 places (21%). Courts also anonymise places the federal rules keep: in a sample of 12 missed
  places, four were a court or a municipality acting as an authority or party ("Bezirksgericht
  Sarnen", "Gemeinde Spiez").
- **The sweep** raised recall from 87.2% to 89.4% with 70B (290 names added) and from 75.8% to
  76.4% with 8B (22 names).
- **The audit points at a third of the misses.** In both runs the second reader and the
  deterministic checks flagged 33% of the gold mentions that leaked, so the clerk sees a risk
  marked at one leak in three.
- **No change outside the edits.** Neither Velum run wrote a free-form change; the diff guard
  makes that a property of the code, not of the model.
- **Cost and throughput.** With 70B a decision took about 22,500 tokens and 85 s of model time
  (the sum of request latencies), and the 537 decisions took 66 minutes with 12 in parallel on the
  shared endpoint. At that rate the 7,883 judgments of 2025 come to about 180 million tokens and
  16 hours. 8B uses about as many tokens and 37 s of model time per decision.
- **8B versus 70B.** 8B loses 13 points of recall, mostly on persons and companies. It makes a
  quarter fewer edits (9,149 against 12,447), which is also why it redacts fewer published names.
  These 8B numbers come from the CSCS
  endpoint; the air-gapped setup runs a 4-bit quantisation of the same model, which I have not
  scored on the test split.

## 6. Limitations

- **The gold is the court's own anonymisation.** VelumBench counts a leak only where the court put
  a placeholder. It cannot show what the court itself missed, and it scores over-redaction only on
  judges, clerks and lawyers, not on authorities or place names.
- **Quasi-identifiers are flagged, not measured.** Occupations, small places combined with dates,
  and unusual events are what re-identifies people in practice. The second reader and the
  deterministic checks point at them, but VelumBench has no gold for them.
- **Coverage.** The generator recognises only "letter + underscores" placeholders, so the Federal
  Criminal Court and most Ticino decisions are missing, and Romansh is not covered. The Zurich pack
  is implemented and unit-tested but not measured, because no Zurich gold exists in this format.
- **No clerk study.** I have not measured how long a clerk needs to check Velum's output, so I
  make no claim about time saved against the 46 minutes of manual work.
- **Determinism.** Temperature 0 on a shared endpoint is not fully deterministic; a re-run can flip
  single mentions.
- **Rule versus practice.** Art. 6 para. 1 keeps court-appointed experts, and Velum follows it.
  Published decisions show that courts sometimes anonymise experts anyway, and VelumBench counts
  those as leaks.

## 7. Reproducibility

- Code: tag `v1.0` of the repository. `make run` builds the image and runs the demo; `make test` runs
  the unit tests; `make bench ARGS="--split test --workers 12"` reruns the Velum rows with the model in
  `LLM_NAME`, `--system rewrite --per-language 20` the baseline, `--system patterns` the pattern row.
- Models: `swiss-ai/Apertus-v1.5-70B` and `-8B` on `https://api.inference.cscs.ch/v1`, runs on
  1 October 2026. Hosted models can change, so the raw outputs of every run are in `results/` and
  each summary recomputes from them without a model call (`results/README.md`).
- Seeds: sampling seed `20261001`, split by `sha256(id) mod 7`, temperature 0.
- Hardware: a MacBook with Docker for Velum; the model ran on the CSCS endpoint, or locally in
  llama.cpp for the air-gapped run.

## 8. Next steps

- Packs for the Federal Administrative Court, the Federal Criminal Court and cantonal courts, with
  their placeholder conventions.
- Learn from the clerk: log accepted and rejected edits in the review page and turn recurring
  corrections into pack rules or extraction examples.
- Measure with a court on decisions as clerks anonymise them in-house, including quasi-identifiers.
- Fine-tune Apertus 8B for extraction on synthetic decisions like VelumBench dev to close the gap
  to 70B for offline use.

## License

Creative Commons Attribution 4.0 (CC-BY-4.0). Code: Apache-2.0. VelumBench: CDLA-Permissive-2.0.

## References

1. Bundesgericht, Regeln für die Anonymisierung der Urteile (2020). bger.ch, Reglemente.
2. Kanton Zürich, «ZHEntscheide»: Anleitung zum Einreichen der zu publizierenden Entscheide (March 2025).
3. Bundesgerichtsgesetz (BGG), SR 173.110, Art. 27; Urheberrechtsgesetz (URG), SR 231.1, Art. 5.
4. Gemeinsame Medienmitteilung der eidgenössischen Gerichte zum Geschäftsbericht 2025 (7,883 judgments).
5. Swiss AI Initiative, Apertus v1.5 8B and 70B. huggingface.co/swiss-ai.
6. J. Hertner, OpenCaseLaw: `voilaj/swiss-caselaw`, Hugging Face, revision 90d5cd21.
7. ggml-org, llama.cpp, release b11312.
8. D. Hürlimann, D. Kettiger, Zugänglichkeit zu Urteilen kantonaler Gerichte: Ergebnisse einer Befragung,
   Justice - Justiz - Giustizia 2018/2, Rz 16 (survey estimates, not measurements).
