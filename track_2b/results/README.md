# Benchmark runs

The raw outputs and summaries behind the tables in the technical report: one run per system on the
VelumBench test split, on 1 October 2026, with the CSCS endpoint at temperature 0.

| Files | Run |
| --- | --- |
| `velum_Apertus-v1.5-70B_bger-2020_test.*` | Velum with Apertus 70B, all 537 decisions (12 in parallel, 66 minutes) |
| `velum_Apertus-v1.5-70B_bger-2020_test.per-language-20.summary.json` | the same rows, scored on the 60 decisions of the rewrite baseline |
| `velum_Apertus-v1.5-8B_bger-2020_test.*` | Velum with Apertus 8B, all 537 decisions (8 in parallel, 89 minutes) |
| `rewrite_Apertus-v1.5-70B_bger-2020_test.*` | the rewrite baseline with Apertus 70B, 60 decisions |
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

Add `--per-language 20` for the 60-decision subset, `--system rewrite` or `--system patterns` for
the other runs.
