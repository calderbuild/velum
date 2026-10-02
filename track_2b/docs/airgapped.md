# Running Velum without a network

Velum reaches Apertus only through an OpenAI-compatible endpoint (`LLM_BASE_URL`). Velum itself
is standard-library Python with no packages to install, so the only other thing it needs is an
Apertus server inside the same perimeter. The three setups differ only in where that server runs:

| Setup | Apertus server | What changes |
| --- | --- | --- |
| Hosted (default `make run`) | CSCS endpoint `https://api.inference.cscs.ch/v1`, Swiss national supercomputing centre | nothing |
| On-premise | Any OpenAI-compatible server in the court's network (vLLM, SGLang or llama.cpp) serving Apertus v1.5 | set `LLM_BASE_URL`, `LLM_NAME`, `LLM_API_KEY` |
| Air-gapped | llama.cpp next to Velum on one machine, on a Docker network with no route out | `make airgapped` |

## Air-gapped run

`compose.airgapped.yml` starts two containers on a Docker network marked `internal: true`. Docker
gives such a network no gateway, so neither container can reach anything outside the machine.

```
 ┌──────────── one machine, network "sealed" (internal) ────────────┐
 │  velum  ──HTTP──>  apertus (llama.cpp server, GGUF from ./models)  │
 └───────────────────────────────────────────────────────────────────┘
```

### 1. Before disconnecting (build time)

Everything that needs the internet happens here, once.

```bash
cd track_2b
mkdir -p models
# Apertus v1.5 8B, text-only conversion quantised to Q4_K_M: 5.06 GB, Apache-2.0.
curl -L -o models/apertus-v1.5-8b-text-q4_k_m.gguf \
  https://huggingface.co/Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF/resolve/main/apertus-v1.5-8b-text-q4_k_m.gguf
shasum -a 256 models/apertus-v1.5-8b-text-q4_k_m.gguf
# expected a037df8d87ff6caacee794ee85f55342f2152e0d359b7389033300c3bee5f299
docker compose -f compose.airgapped.yml pull apertus   # llama.cpp server, 1.2 GB
docker compose -f compose.airgapped.yml build velum    # python:3.12-slim plus Velum
```

To use the 8-bit model instead (8.57 GB, sha256 `dea904ad80cd725ec89962abae464477f5d8114d1f4377514f381f7dc2ed202d`),
download `apertus-v1.5-8b-text-q8_0.gguf` from `andreasmartin/apertus-v1.5-8b-text-Q8_0-GGUF` and set
`GGUF=apertus-v1.5-8b-text-q8_0.gguf`.

Both files are community conversions of the text part of `swiss-ai/Apertus-v1.5-8B` (GGUF
architecture `apertus`). A court that does not want to trust a third-party conversion can convert
the official weights itself with llama.cpp's `convert_hf_to_gguf.py`; I have not tested that path.

### 2. Disconnected (runtime)

```bash
make airgapped
```

This starts llama.cpp, waits for its health check, then runs the same demo as `make run`: three
decisions, extraction, rule pack, sweep and second reader, all against the local model. Nothing is
downloaded at runtime.

To check the isolation yourself, run this before or after `make airgapped`, not during it: the
run stops as soon as any container on its network exits.

```bash
docker compose -f compose.airgapped.yml run --rm velum \
  python -c "import urllib.request; urllib.request.urlopen('https://huggingface.co', timeout=5)"
# fails: the container has no route out
```

### Hardware

The 8B Q4_K_M model runs on CPU. Give Docker at least 10 GB: the llama.cpp container peaked at
8.8 GiB in the tested run below, and on a Docker VM with 7.65 GiB the server was killed for lack of
memory. On a GPU machine, replace the image tag `server-b11312` with `server-cuda-b11312`, which is
the same llama.cpp build compiled for CUDA.

### Tested run (2 October 2026)

Mac mini (Apple silicon, 24 GB), Docker in a colima VM with 8 CPUs and 12 GB, CPU only:

| Decision | Language | Time | Identities removed | Judges, clerks, lawyers kept |
| --- | --- | ---: | ---: | ---: |
| 4A_172/2025 | de | 157 s | 10/10 | 9/9 |
| 1C_92/2025 | fr | 171 s | 14/15 | 7/7 |
| 4A_193/2020 | it | 145 s | 8/8 | 5/5 |

`make airgapped` took 8 minutes from start to exit, including loading the model. The isolation check
above, run afterwards on the same network, failed on DNS for `huggingface.co` and with "Network is
unreachable" for `1.1.1.1`. Three decisions are a smoke test, not a score: I have not run the test
split against the quantised model.

## Build time versus runtime

| Dependency | When | Needed for |
| --- | --- | --- |
| `python:3.12-slim` image | build | Velum container |
| `ghcr.io/ggml-org/llama.cpp:server-b11312` | build | air-gapped setup only |
| GGUF model file | build | air-gapped setup only |
| Apertus endpoint (`LLM_BASE_URL`) | runtime | every setup; inside the perimeter for on-premise and air-gapped |
| Anything else | never | Velum makes no other network request; the review page loads no fonts, scripts or images from outside |
