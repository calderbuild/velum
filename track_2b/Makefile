IMAGE := velum
PORT ?= 8000
LLM := -e LLM_NAME -e LLM_BASE_URL -e LLM_API_KEY

.PHONY: run demo bench test image airgapped

# Anonymise the demo decisions with Apertus, then serve the review interface on http://localhost:$(PORT).
run: image
	docker run --rm --init $(LLM) -p 127.0.0.1:$(PORT):8000 $(IMAGE)

# Same pipeline, printed to the terminal only.
demo: image
	docker run --rm --init $(LLM) $(IMAGE) python -m velum demo

# Score on VelumBench, e.g. make bench ARGS="--split dev --limit 20". Results land in ./out/bench.
bench: image
	mkdir -p out
	docker run --rm --init $(LLM) --user $$(id -u):$$(id -g) -v "$(CURDIR)/out:/app/out" $(IMAGE) python -m velum bench $(ARGS)

# Unit tests for the deterministic parts; no model needed.
test: image
	docker run --rm $(IMAGE) python -m unittest discover -s src

image:
	docker build -q -t $(IMAGE) .

# Apertus served by llama.cpp next to Velum on a Docker network with no route out (see docs/airgapped.md).
airgapped:
	docker compose -f compose.airgapped.yml up --build --abort-on-container-exit velum
