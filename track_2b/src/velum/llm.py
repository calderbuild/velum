"""OpenAI-compatible chat client. Configured only through LLM_NAME, LLM_BASE_URL and LLM_API_KEY."""

import json
import os
import time
import urllib.error
import urllib.request

RETRY_STATUS = {408, 429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    def __init__(self, message, partial=None, usage=None):
        super().__init__(message)
        self.partial = partial  # for a reply cut off at max_tokens: what the model wrote until then
        self.usage = usage


def config():
    missing = [
        k for k in ("LLM_NAME", "LLM_BASE_URL", "LLM_API_KEY") if not os.environ.get(k)
    ]
    if missing:
        raise SystemExit(f"missing environment variable(s): {', '.join(missing)}")
    return (
        os.environ["LLM_NAME"],
        os.environ["LLM_BASE_URL"].rstrip("/"),
        os.environ["LLM_API_KEY"],
    )


def chat_json(system, user, schema, max_tokens=3000):
    """One deterministic chat completion constrained to a JSON schema. Returns (data, usage)."""
    model, base, key = config()
    body = {
        "model": model,
        "temperature": 0,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "velum", "schema": schema, "strict": True},
        },
        "chat_template_kwargs": {"enable_thinking": False},
    }
    started = time.time()
    reply = _post(f"{base}/chat/completions", key, body)
    choice = reply["choices"][0]
    usage = dict(reply.get("usage") or {}, seconds=round(time.time() - started, 2))
    if choice.get("finish_reason") == "length":
        raise LLMError(f"output hit max_tokens={max_tokens}", choice["message"].get("content") or "", usage)
    try:
        return json.loads(choice["message"]["content"]), usage
    except json.JSONDecodeError as e:
        raise LLMError(f"model returned invalid JSON: {e}") from e


def chat_list(system, user, schema, max_tokens):
    """For a schema whose one property is a list: (items, usage). A reply cut off at max_tokens
    keeps its complete items; the repetition that usually causes the cut adds nothing new."""
    try:
        data, usage = chat_json(system, user, schema, max_tokens)
        return data[next(iter(schema["properties"]))], usage
    except LLMError as e:
        if e.partial is None:
            raise
        return salvage_items(e.partial), e.usage


def salvage_items(partial):
    """The complete objects of the first list in a reply that was cut off."""
    decoder, items = json.JSONDecoder(), []
    pos = partial.find("[")
    while pos != -1:
        start = partial.find("{", pos + 1)
        if start == -1:
            break
        try:
            item, pos = decoder.raw_decode(partial, start)
        except json.JSONDecodeError:
            break
        items.append(item)
    return items


def chat_text(system, user, max_tokens):
    """Plain completion, used only by the rewrite baseline. Returns (text, usage, cut_off)."""
    model, base, key = config()
    body = {
        "model": model,
        "temperature": 0,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "chat_template_kwargs": {"enable_thinking": False},
    }
    started = time.time()
    reply = _post(f"{base}/chat/completions", key, body)
    choice = reply["choices"][0]
    usage = dict(reply.get("usage") or {}, seconds=round(time.time() - started, 2))
    return choice["message"]["content"] or "", usage, choice.get("finish_reason") == "length"


def _post(url, key, body, attempts=5):
    data = json.dumps(body).encode()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, data, headers), timeout=300
            ) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            if e.code not in RETRY_STATUS or attempt == attempts - 1:
                raise LLMError(f"HTTP {e.code} from {url}: {detail}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == attempts - 1:
                raise LLMError(f"cannot reach {url}: {e}") from e
        time.sleep(2 ** (attempt + 1))
    raise LLMError(f"no attempts made for {url}")
