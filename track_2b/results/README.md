# Benchmark runs

The raw outputs and summaries behind the tables in the technical report: one run per system on the
VelumBench test split, on 1 October 2026, with the CSCS endpoint at temperature 0.

| Files | Run |
| --- | --- |
| `velum_Apertus-v1.5-70B_bger-2020_test.*` | Velum with Apertus 70B, all 537 decisions (12 in parallel, 66 minutes) |
| `velum_Apertus-v1.5-70B_bger-2020_test.per-language-20.summary.json` | the same rows, scored on the 60 decisions of the rewrite baseline |
| `velum_Apertus-v1.5-8B_bger-2020_test.*` | Velum with Apertus 8B, all 537 decisions (8 in parallel, 89 minutes) |
| `rewrite_Apertus-v1.5-70B_bger-2020_test.*` | the rewrite baseline with Apertus 70B on the same 60 decisions |
| `patterns_none_bger-2020_test.*` | regular expressions only, no model |

Each line of a `.jsonl.gz` file is one decision: the output text, every edit with its article, the
risks the audit raised, the score and the token usage. A summary recomputes from its raw output
without a model call: every decision is already in the file, so the benchmark has nothing left to
send and only scores.

```bash
cd track_2b/src
mkdir -p /tmp/runs
gunzip -c ../results/velum_Apertus-v1.5-70B_bger-2020_test.jsonl.gz > /tmp/runs/velum_Apertus-v1.5-70B_bger-2020_test.jsonl
LLM_NAME=swiss-ai/Apertus-v1.5-70B LLM_BASE_URL=http://127.0.0.1:9 LLM_API_KEY=unused \
  python3 -m velum bench --split test --out /tmp/runs
```

Set `LLM_NAME` to the model of the run (`swiss-ai/Apertus-v1.5-8B` for the 8B file), since the file
name follows it. Add `--per-language 20` for the 60-decision subset (its summary goes to a file of its own),
`--system rewrite --per-language 20` for the baseline and `--system patterns` for the pattern run.
Run the baseline only with `--per-language 20`: its file holds those 60 decisions, so without the
option the benchmark would send the other 477 to the model.
