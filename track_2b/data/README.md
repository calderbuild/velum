# Data

| Path | What it is | Size |
| --- | --- | --- |
| `velumbench/dev.jsonl` | 79 decisions, the only split I looked at while writing prompts and rules | 3.1 MB |
| `velumbench/test.jsonl` | 537 held-out decisions, used once for the reported numbers | 18.9 MB |
| `demo/cases.jsonl` | 3 short decisions from the test split (de, fr, it) that `make run` anonymises | 30 KB |

## VelumBench

VelumBench is a test set for anonymising Swiss court decisions in German, French and Italian.
It is built from decisions the courts have already published, so it never contains a real party's name.

**How a case is made.** A published decision has placeholders such as `A.________` in the
places where the court removed a party. `python -m velum build` (code in `src/velum/bench.py`)
puts an invented Swiss identity in each placeholder, the same one for every occurrence of the
same letter. The result reads like a decision before anonymisation, and the inserted spans are
the exact gold for what a system must remove. When a party in the header is followed by an
address line, the generator also inserts an invented street address (the courts drop those
entirely, so the published text has nothing to fill). The generator decides from the context
whether a letter stands for a person, a company or a place. Names come from per-language pools,
and no word of an inserted person, company or place name occurs in the source decision.

**What must stay.** Judges, clerks and lawyers are named on purpose (BGer rules Art. 4 Abs. 1
lit. g and Art. 5 Abs. 1). The generator reads them from the composition block and from "vertreten durch /
représenté par / patrocinato da" and stores them under `keep`. Removing one of them counts as
over-redaction.

**Split.** `sha256(decision_id) mod 7 == 0` goes to dev, the rest to test. I used dev for all
prompt and rule work and ran the test split once, on the final code.

| | dev | test |
| --- | --- | --- |
| Decisions | 79 (de 18, fr 36, it 25) | 537 (de 198, fr 180, it 159) |
| Courts | BGer 56, BVGer 9, GE 8, VD 2, TI 2, ZH 1, BE 1 | BGer 356, BVGer 80, ZH Obergericht 24, BE 24, VD 23, GE 17, GR 9, TI 4 |
| Gold mentions to remove | 1,459 (person 1,187, company 187, address 52, place 33) | 8,390 (person 6,713, company 951, address 374, place 352) |
| Distinct gold entities | 376 | 2,471 |
| Published names that must stay | 450 mentions (298 names) | 3,168 mentions (2,072 names) |
| Decision dates | 2008 to 2026 | 2008 to 2026 |
| Median length | 13,685 characters | 13,088 characters |

### Fields

| Field | Meaning |
| --- | --- |
| `id`, `court`, `language`, `docket`, `decision_date`, `legal_area`, `source_url` | From the source row |
| `text` | The decision with invented identities in place of the placeholders: the system input |
| `gold` | `{start, end, text, entity, kind}` per inserted mention; `kind` is person, company, place or address; `entity` groups mentions of the same party (`A`, `A#address`) |
| `keep` | `{text, kind, count}` for each published name that must stay (`court_official` or `lawyer`) |
| `published_text` | The decision exactly as the court published it |
| `license` | Instance-level licence note |
| `provenance` | `{hf_dataset, revision, file, row_group, file_row_number, content_hash}`, enough to re-fetch the source row |

### Source and licence

- Source rows: [`voilaj/swiss-caselaw`](https://huggingface.co/datasets/voilaj/swiss-caselaw) at revision
  `90d5cd212466d4286ed574f825ae5b3df8cb3645` (CC0-1.0). I drew a stratified sample of 750 decisions
  (BGer 420, BVGer 90, BStGer 90, six cantonal courts 150) with a fixed seed, reading only the needed row
  groups. 616 of them yielded at least one gold mention.
- Decision texts are official decisions and are not protected by copyright (Art. 5 para. 1 let. c URG,
  SR 231.1). The court's own publication stays authoritative.
- The invented identities, the gold and keep annotations and the split are released under
  CDLA-Permissive-2.0, the dataset licence of the hackathon.

### Personal data

- No real party is re-identified. Every person, company and place in `gold` is invented, and none of
  its words occurs in the source decision. Addresses combine common Swiss street names with real
  postcodes and towns.
- Judges, clerks and lawyers appear as the courts published them. Swiss courts publish these names on
  purpose.
- The source dataset warns that some cantonal decisions may still contain names the court missed.
  VelumBench does not add any, but it keeps whatever the court published. If a court withdraws or
  re-anonymises a decision, I will remove the case. Contact: open an issue in this repository.

### Known gaps

- **Gold is only as complete as the court's own anonymisation.** If a court left a name in the
  published text, VelumBench does not count it as a leak.
- **Placeholder styles.** Only "letter + period + underscores" is recognised. The Federal Criminal Court
  (bare `A.`) and most Ticino decisions (`RE 1`, bare underscores) are therefore missing.
- **Courts that anonymise lawyers.** Their lawyer placeholders stay as they are and are not scored.
- **Addresses** are inserted only for the first party in the header, as `street, postcode town`.
- **Kind of a placeholder** (person, company, place) is decided by surrounding words, so a few
  companies are scored as persons and the reverse. Recall does not depend on the kind.
