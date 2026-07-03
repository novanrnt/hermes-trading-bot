"""
LLM API call with retry logic — proven pattern for pipeline orchestrators.
Drop this into any _call_llm() that talks to an OpenAI-compatible /v1/chat/completions endpoint.

Coverage:
  - HTTP errors (retry)
  - Connection/timeout (URLError, socket.timeout, TimeoutError, ConnectionError) (retry)
  - Empty response body (retry)
  - Malformed JSON from API (retry)
  - Empty choices[0].message.content (retry)
  - JSON extraction failure in _extract_json() (retry)

MAX_RETRIES=2, RETRY_DELAY=2s. Log format: [RETRY X/2] <reason>, waiting 2s...
"""

import json
import socket
import time
import urllib.request
import urllib.error

REQUEST_TIMEOUT = 120  # seconds per call
MAX_RETRIES = 2
RETRY_DELAY = 2


def _get_api_key() -> str:
    """Replace with your actual key loader."""
    return ""


def _extract_json(text: str) -> dict:
    """Extract JSON object from LLM response (handles ```json fences)."""
    import re
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in response. First 200 chars: {text[:200]}")
    return json.loads(text[start:end + 1])


def _call_llm(system_prompt: str, api_config: dict) -> dict:
    """Call LLM API and return parsed JSON. Retries on empty/error responses."""
    url = f"{api_config['base_url'].rstrip('/')}/chat/completions"
    model = api_config["default_model"]

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Run analysis now."},
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
    }

    data = json.dumps(payload).encode("utf-8")
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {_get_api_key()}",
                },
            )
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                raw = resp.read().decode("utf-8")

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"HTTP {e.code}: {error_body[:300]}")
            if attempt < MAX_RETRIES:
                print(f"[RETRY {attempt+1}/{MAX_RETRIES}] HTTP {e.code}, waiting {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                continue
            raise last_error

        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
            last_error = RuntimeError(f"Connection/timeout error: {e}")
            if attempt < MAX_RETRIES:
                print(f"[RETRY {attempt+1}/{MAX_RETRIES}] {type(e).__name__}: {e}, waiting {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                continue
            raise last_error

        except Exception as e:
            last_error = RuntimeError(f"API call failed: {e}")
            if attempt < MAX_RETRIES:
                print(f"[RETRY {attempt+1}/{MAX_RETRIES}] {e}, waiting {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                continue
            raise last_error

        # Validate response body
        if not raw or not raw.strip():
            last_error = ValueError("Empty response body from LLM API")
            if attempt < MAX_RETRIES:
                print(f"[RETRY {attempt+1}/{MAX_RETRIES}] Empty response, waiting {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                continue
            raise last_error

        try:
            result = json.loads(raw)
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            last_error = RuntimeError(f"Malformed API response: {e}")
            if attempt < MAX_RETRIES:
                print(f"[RETRY {attempt+1}/{MAX_RETRIES}] Malformed response: {e}, waiting {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                continue
            raise last_error

        # Validate content
        if not content or not content.strip():
            last_error = ValueError("Empty content in LLM response")
            if attempt < MAX_RETRIES:
                print(f"[RETRY {attempt+1}/{MAX_RETRIES}] Empty content, waiting {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                continue
            raise last_error

        try:
            return _extract_json(content)
        except (ValueError, json.JSONDecodeError) as e:
            last_error = e
            if attempt < MAX_RETRIES:
                print(f"[RETRY {attempt+1}/{MAX_RETRIES}] JSON extraction failed: {e}, waiting {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                continue
            raise

    if last_error:
        raise last_error
    raise RuntimeError("Unknown error in _call_llm (all retries exhausted)")
