# GLC v1 — ElevenLabs TTS: Team Task Handbook

> **Team:** Group ElevenLabs · **Slot:** `elevenlabs`  
> **Deadline:** 2026-07-05  
> **PR markers required:** `# Group: Group ElevenLabs` and `# Slot: elevenlabs`

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Module Interaction Map](#3-module-interaction-map)
4. [Scope — What This Team Owns](#4-scope--what-this-team-owns)
5. [Files Requiring Work](#5-files-requiring-work)
6. [Implementation Contract](#6-implementation-contract)
7. [Team Members & Task Distribution](#7-team-members--task-distribution)
8. [Dependency Graph](#8-dependency-graph)
9. [Collaboration Workflow](#9-collaboration-workflow)
10. [Suggested Timeline (4-Person)](#10-suggested-timeline-4-person)
11. [Running Tests](#11-running-tests)
12. [Risks and Recommendations](#12-risks-and-recommendations)

---

## 1. Project Overview

**GLC v1** is a *Gateway for LLMs and Channels* running on port **8111**. It has two major layers:

**Layer 1 — LLM Gateway (inherited from V9):**  
`/v1/chat`, `/v1/vision`, `/v1/embed`, `/v1/cost`, `/v1/providers` — fully implemented, no changes needed.

**Layer 2 — Channel + Voice layer (new in S11):**
- `POST /v1/speak` → TTS dispatcher → one of five providers
- `POST /v1/transcribe` → STT dispatcher → one of three providers
- `WS /v1/channels/{name}` → channel adapter control plane
- `/v1/control/*` → out-of-band kill switch, pairing

**Security layers running across both:**
- Policy engine (`glc/policy/`) — evaluates every tool call outside the LLM context
- Trust-level classifier (`glc/security/trust_level.py`) — classifies every inbound message
- Audit log (`glc/audit/`) — append-only, per-row commits
- Pairing store — rotating 6-digit codes, TTL-enforced

---

## 2. Architecture

```
HTTP Client
    │
    ▼
glc/routes/speak.py          ← POST /v1/speak
    │
    ▼
glc/voice/tts/router.py      ← prefer="quality" → "elevenlabs"
    │
    ▼
glc/voice/tts/providers/
    elevenlabs/adapter.py    ← THIS TEAM'S WORK (currently a stub)
    │
    ├── glc/voice/tts/base.py        (TTSProvider ABC, SynthesizeResult, TTSError)
    └── ElevenLabs API upstream
```

The router maps `prefer="quality"` → `"elevenlabs"`. When a client calls `POST /v1/speak` with `prefer=quality`, the router dynamically imports `glc.voice.tts.providers.elevenlabs.adapter`, instantiates `Provider()`, and calls `await provider.synthesize(text, voice_id)`.

---

## 3. Module Interaction Map

| Module | Role |
|---|---|
| `glc/routes/speak.py` | HTTP route handler — calls the TTS router |
| `glc/voice/tts/router.py` | Maps `prefer` field to the correct provider |
| `glc/voice/tts/base.py` | `TTSProvider` ABC, `SynthesizeResult` dataclass, `TTSError` exception |
| `glc/voice/tts/providers/elevenlabs/adapter.py` | **Your implementation** |
| `glc/voice/tts/providers/elevenlabs/schemas.py` | Pydantic types for request/response shapes |
| `tests/voice/tts/test_elevenlabs.py` | 7 tests — **do not modify** |
| `tests/voice/tts/mocks/elevenlabs_mock.py` | Mock API fake — **do not modify** |

---

## 4. Scope — What This Team Owns

Per `GROUPS.md`, the owned paths are:

```
glc/voice/tts/providers/elevenlabs/
glc/voice/tts/providers/elevenlabs/**
```

> **Hard boundary:** The CI check (`scripts/check_pr_boundaries.py`) **rejects any PR that modifies files outside these paths.** Do not touch `router.py`, `base.py`, `routes/speak.py`, `pyproject.toml`, or any test file outside the owned paths — not even to fix a typo.

---

## 5. Files Requiring Work

### Files This Team Must Deliver

| File | Current State | Required Work |
|---|---|---|
| `glc/voice/tts/providers/elevenlabs/adapter.py` | Stub — raises `NotImplementedError` | Full implementation of `synthesize()` |
| `glc/voice/tts/providers/elevenlabs/schemas.py` | Empty (2 lines — just the module docstring and `from __future__ import annotations`) | Pydantic types for ElevenLabs request/response shapes |

### Files Already Provided (Read-Only)

| File | Purpose |
|---|---|
| `tests/voice/tts/test_elevenlabs.py` | 7 tests — must all pass |
| `tests/voice/tts/mocks/elevenlabs_mock.py` | Mock API fake used by tests |
| `glc/voice/tts/base.py` | `TTSProvider` ABC, `SynthesizeResult`, `TTSError` |
| `glc/voice/tts/router.py` | Dispatcher — wires `prefer=quality` to this adapter |
| `glc/routes/speak.py` | HTTP route that calls the router |
| `glc/voice/tts/providers/elevenlabs/README.md` | Provider-specific quirks reference |

---

## 6. Implementation Contract

### 6.1 Behavioural Requirements (derived from tests + README)

| Requirement | Verified By |
|---|---|
| `Provider.name == "elevenlabs"` | `test_provider_name_matches` |
| Returns a valid `SynthesizeResult` with `provider="elevenlabs"`, non-empty `audio_b64`, `sample_rate > 0` | `test_synthesize_returns_synthesize_result` |
| Records `text_len` (total original length, not per-chunk) in the upstream call | `test_synthesize_passes_text_to_upstream` |
| Respects `canned_sample_rate` from mock | `test_synthesize_records_sample_rate` |
| Propagates upstream errors as `TTSError` with the correct HTTP status code | `test_synthesize_propagates_upstream_error` |
| Handles empty text gracefully — returns a valid `SynthesizeResult`, does not crash | `test_synthesize_handles_empty_text` |
| Tracks monthly char usage; raises `TTSError(status=429)` with "quota" or "limit" in message **before** sending when quota would be exceeded | `test_channel_specific_behaviour_free_tier_quota_tracking` |
| When `config["mock"]` is present, delegates directly to `mock.synthesize()` | All 7 tests (mock pattern) |

### 6.2 Real API Specification

| Property | Value |
|---|---|
| **Endpoint** | `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}` |
| **Auth header** | `xi-api-key: <KEY>` — **NOT** `Authorization: Bearer` |
| **Request body** | `{"text": "...", "model_id": "eleven_flash_v2_5"}` |
| **Response body** | Raw MP3 bytes — encode with `base64.b64encode(response.content).decode("ascii")` |
| **Default output** | MP3 at 44.1 kHz |
| **Default `voice_id`** | `21m00Tcm4TlvDq8ikWAM` (Rachel) |
| **Free tier limit** | 10,000 chars/month |
| **Per-request limit** | ~5,000 chars — chunk longer text before sending |
| **HTTP client** | `httpx` (already in `pyproject.toml` dependencies) |

### 6.3 Mock Behaviour Contract

The `ElevenlabsMock` (from `tests/voice/tts/mocks/elevenlabs_mock.py`) exposes:

| Attribute | Type | Purpose |
|---|---|---|
| `canned_audio_b64` | `str` | The base64 audio string returned on success |
| `canned_mime` | `str` | MIME type returned (`"audio/wav"` in tests) |
| `canned_sample_rate` | `int` | The sample rate returned — adapter must honour this |
| `received_calls` | `list[dict]` | Appended on every call with `{"text_len": len(text), "voice_id": voice_id}` |
| `upstream_failure` | `tuple[int, str] \| None` | If set, mock raises `TTSError(msg, status=code)` |
| `monthly_chars_used` | `int` | Chars consumed so far this month |
| `monthly_chars_limit` | `int` | Cap (default 10,000) |

### 6.4 Architectural Decisions (set before coding begins)

These decisions are fixed to prevent merge conflicts:

1. **Mock delegation pattern** — first line of `synthesize()`: `if mock := self.config.get("mock"): return await mock.synthesize(text, voice_id)`
2. **Quota check** — implemented as a `_check_quota(text, mock)` method; runs **before** any HTTP call or mock delegation for the real path; for the mock path the quota check reads `mock.monthly_chars_used` and `mock.monthly_chars_limit`
3. **Chunking** — implemented as a standalone `_chunk_text(text: str, max_chars: int = 5000) -> list[str]` function; splits on sentence boundaries (`.`, `?`, `!`); a single token longer than 5000 chars is sent as one chunk
4. **Audio merge** — concatenate raw bytes from all chunks before a single `base64.b64encode()` call
5. **HTTP wrapper** — implemented as a private `_call_upstream(text: str, voice_id: str) -> bytes` coroutine to isolate error handling
6. **Quota state (real path)** — stored in `~/.glc/elevenlabs_quota.json` with a `YYYY-MM` month key
7. **`text_len` recording** — always the **total** original `len(text)`, not the per-chunk length

---

## 7. Team Members & Task Distribution

### Member Overview

| Member | Primary Role | Key Responsibilities |
|---|---|---|
| **Hari Prasath** | Team Management + Skeleton | Architecture, adapter skeleton, integration, PR |
| **Nawaz Ali** | Research + Schemas | Test/mock analysis, API research, Pydantic schemas |
| **Anshul Agarwal** | HTTP + Chunking + Live API | Real API call, text chunking, live integration test |
| **Vichitravir Dwivedi** | Quota + Errors + Quality | Quota tracking, error handling, lint/type compliance |

---

### Hari Prasath — Team Management + Adapter Skeleton

**Objective:** Establish the project foundation, define the internal contract, implement the adapter skeleton and mock delegation path, integrate all members' contributions, and submit the final PR.

**Responsibilities:**
- Define the architectural decisions in §6.4 before any coding begins — communicate these to all members on Day 1
- Create the team feature branch `feat/elevenlabs-tts`
- Implement the adapter skeleton with `__init__`, config injection, environment variable reading, and mock delegation
- Integrate all sub-branches sequentially: skeleton → HTTP → chunking → quota → errors
- Review every member's contribution before merging into the team branch
- Perform the final end-to-end integration pass
- Open the implementation PR with the required CI markers

**Deliverables:**

```python
# adapter.py skeleton (Day 1)
import os
from __future__ import annotations

import httpx

from glc.voice.tts.base import SynthesizeResult, TTSError, TTSProvider
from glc.voice.tts.providers.elevenlabs.schemas import ElevenLabsRequest

DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"

class Provider(TTSProvider):
    name = "elevenlabs"

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self._api_key = os.environ.get("ELEVENLABS_API_KEY", "")
        self._voice_id = os.environ.get("ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID)

    async def synthesize(self, text: str, voice_id: str | None = None) -> SynthesizeResult:
        mock = self.config.get("mock")
        if mock is not None:
            self._check_quota(text, mock)        # quota check even in mock path
            return await mock.synthesize(text, voice_id)

        # TODO (Anshul): _check_quota for real path, _chunk_text, _call_upstream
        raise NotImplementedError("real path TBD — see TODO markers")

    def _check_quota(self, text: str, mock=None) -> None:
        # TODO (Vichitravir): implement
        pass

    async def _call_upstream(self, text: str, voice_id: str) -> bytes:
        # TODO (Anshul): implement
        raise NotImplementedError

    @staticmethod
    def _chunk_text(text: str, max_chars: int = 5000) -> list[str]:
        # TODO (Anshul): implement
        return [text]
```

- Create `feat/elevenlabs-tts` branch and push the skeleton
- Review M8's schemas, M5's HTTP call, M6's chunking, M7's quota, M10's error handling
- Merge sub-branches in the order: skeleton → schemas → HTTP → chunking → quota → errors → lint
- Final PR description must contain:
  ```
  # Group: Group ElevenLabs
  # Slot: elevenlabs
  ```

**Unblocked from:** Day 1  
**Effort:** ~5–7 hours spread across the sprint  
**Blocks:** Everyone (skeleton must land before others can build on it)

---

### Nawaz Ali — Research + Pydantic Schemas

**Objective:** Analyze the tests and mock to produce the behavioural specification; research the real ElevenLabs API; define Pydantic types in `schemas.py`.

**Responsibilities:**

**Phase A — Test & Mock Analysis (Day 1, parallel)**
- Read `tests/voice/tts/test_elevenlabs.py` in full
- Read `tests/voice/tts/mocks/elevenlabs_mock.py` in full
- Produce a written spec mapping each of the 7 tests to the exact adapter behaviour it requires
- Specifically document: how `monthly_chars_used` / `monthly_chars_limit` work, what `received_calls` records, how `upstream_failure` triggers, what `canned_sample_rate` does
- Share this spec with the team (post in team chat / add as code comments in adapter.py)

**Phase B — API Research (Day 1, parallel)**
- Research the ElevenLabs Flash v2.5 API: `https://elevenlabs.io/docs/api-reference/text-to-speech`
- Document: exact endpoint URL, required headers, JSON body fields, response format (confirm raw MP3 bytes vs. JSON wrapper), rate limit/quota error shapes and status codes
- Share findings with Anshul and Hari before Day 2

**Phase C — Pydantic Schemas (Day 2)**
- Implement `glc/voice/tts/providers/elevenlabs/schemas.py`:

```python
from __future__ import annotations
from pydantic import BaseModel

class ElevenLabsVoiceSettings(BaseModel):
    stability: float = 0.5
    similarity_boost: float = 0.75

class ElevenLabsRequest(BaseModel):
    text: str
    model_id: str = "eleven_flash_v2_5"
    voice_settings: ElevenLabsVoiceSettings | None = None
```

- Add any additional types identified from the API docs (e.g., error response shapes)
- Ensure `schemas.py` passes `ruff` and `mypy` before handing off

**Deliverables:**
- Written behavioural spec (shared document or comments in adapter.py)
- API contract document (shared with team)
- Complete `schemas.py` on a sub-branch `feat/elevenlabs-tts/schemas`

**Dependencies:** None (unblocked from Day 1)  
**Effort:** ~5–7 hours total (2–3h research, 2–3h schemas)  
**Blocks:** Anshul (needs API contract for HTTP call), Hari (needs schemas for skeleton imports)

---

### Anshul Agarwal — HTTP Call + Text Chunking + Live API Integration

**Objective:** Implement the real ElevenLabs API HTTP call, text chunking for the free tier, and validate the adapter against the live API.

**Responsibilities:**

**Phase A — HTTP Call + Response Parsing (Day 2–3)**
- Implement `_call_upstream(text, voice_id) -> bytes` in adapter.py:
  - `async with httpx.AsyncClient() as client:` POST to `https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`
  - Set header `xi-api-key: <ELEVENLABS_API_KEY>`
  - Construct the request body using `ElevenLabsRequest(text=text).model_dump(exclude_none=True)`
  - Raise `httpx.HTTPStatusError` on non-2xx responses (use `response.raise_for_status()`)
  - Return `response.content` (raw MP3 bytes)
- Populate `SynthesizeResult` with:
  - `audio_b64 = base64.b64encode(audio_bytes).decode("ascii")`
  - `mime = "audio/mpeg"`
  - `sample_rate = 44100`
  - `provider = "elevenlabs"`
  - `cost_usd = 0.0`

**Phase B — Text Chunking (Day 3)**
- Implement `_chunk_text(text: str, max_chars: int = 5000) -> list[str]`:
  - Split on sentence boundaries (`.`, `?`, `!`) to avoid cutting mid-word
  - A single token longer than 5000 chars must be sent as one chunk (no mid-word splits)
  - Empty string must return `[""]` or `[]` — must not crash
- In `synthesize()`, if `len(text) > 5000`, call `_call_upstream()` once per chunk and concatenate raw bytes before base64-encoding
- `text_len` recorded in `received_calls` must be total original `len(text)`, not per-chunk

**Phase C — Live API Integration (Day 3–4)**
- Obtain a free ElevenLabs API key from `elevenlabs.io`
- Set `ELEVENLABS_API_KEY` and optionally `ELEVENLABS_VOICE_ID` in environment
- Run the adapter against the real API and confirm audio bytes are returned
- Write one additional test `test_live_synthesize` in `tests/voice/tts/` marked `@pytest.mark.requires_live_api`:

```python
@pytest.mark.requires_live_api
@pytest.mark.asyncio
async def test_live_synthesize():
    """Calls the real ElevenLabs API. Requires ELEVENLABS_API_KEY in env."""
    import os
    from glc.voice.tts.providers.elevenlabs.adapter import Provider
    from glc.voice.tts.base import SynthesizeResult
    adapter = Provider()
    r = await adapter.synthesize("Hello from the live API test.")
    assert isinstance(r, SynthesizeResult)
    assert r.audio_b64
    assert r.sample_rate > 0
```

- Document in team notes: how to set env vars, how to run local tests, actual free-tier limits observed

**Deliverables:**
- `_call_upstream()` coroutine on sub-branch `feat/elevenlabs-tts/http`
- `_chunk_text()` function on sub-branch `feat/elevenlabs-tts/chunking`
- `test_live_synthesize` (marked `requires_live_api`, CI skips it) on sub-branch `feat/elevenlabs-tts/live`
- All chunking edge cases handled (empty text, oversized single token)

**Dependencies:**
- Hari's skeleton must be merged first (needs `_call_upstream` stub + `_chunk_text` stub in place)
- Nawaz's API contract (needs exact endpoint, headers, response format)
- Nawaz's `ElevenLabsRequest` schema (uses it for request body construction)

**Effort:** ~6–8 hours total  
**Suggested order:** Start Day 2 after Hari pushes skeleton; API call first, then chunking, then live test

---

### Vichitravir Dwivedi — Quota Tracking + Error Handling + Lint/Type Compliance

**Objective:** Implement the monthly quota pre-flight check, upstream error propagation, and ensure the full codebase passes `ruff` and `mypy` before the PR opens.

**Responsibilities:**

**Phase A — Quota Tracking (Day 3)**
- Implement `_check_quota(text: str, mock=None) -> None` in adapter.py:
  - **Mock path:** read `mock.monthly_chars_used` and `mock.monthly_chars_limit`
  - **Real path:** read/write `~/.glc/elevenlabs_quota.json` keyed by `YYYY-MM`; load `monthly_chars_used` from file; use `monthly_chars_limit = 10_000`
  - If `monthly_chars_used + len(text) > monthly_chars_limit`: raise `TTSError("monthly quota limit exceeded", status=429)`
  - The message **must** contain "quota" or "limit" (case-insensitive) — tests check for this
  - This check must run **before** any HTTP request or mock delegation
  - On the real path, increment and persist the counter after a successful `_call_upstream()` call

- `test_channel_specific_behaviour_free_tier_quota_tracking` must pass after this work

**Phase B — Error Handling (Day 3–4)**
- Wrap `_call_upstream()` to catch and re-raise errors:
  - `httpx.HTTPStatusError` → `TTSError(str(e), status=e.response.status_code)`
  - `httpx.RequestError` (network failures) → `TTSError(str(e), status=503)`
- The mock path already raises `TTSError` directly from `ElevenlabsMock.synthesize()` — no additional wrapping needed there
- `test_synthesize_propagates_upstream_error` must pass (mock injects `upstream_failure = (502, "upstream broken")`)
- Empty text must return a valid `SynthesizeResult` — add a short-circuit guard: if `not text`, return `SynthesizeResult(audio_b64="", mime="audio/mpeg", sample_rate=44100, provider="elevenlabs")`

**Phase C — Type Annotations + Lint Compliance (Day 4–5)**
- Ensure all files in `glc/voice/tts/providers/elevenlabs/` have `from __future__ import annotations` at the top
- Add full type annotations to all functions and methods in `adapter.py` and `schemas.py`
- Run `ruff check glc/voice/tts/providers/elevenlabs/` and fix all violations
- Run `mypy glc/voice/tts/providers/elevenlabs/` and resolve all errors (note: `mypy` is run with `strict=False` per `pyproject.toml`)
- Confirm compliance with:
  - `line-length = 110` (ruff config)
  - `target-version = py311`
  - `select = ["E", "F", "I", "W", "UP", "B"]` — especially `B` rules (no bare `except:`, no shadowing builtins)
- No unused imports, no bare `except:`
- Run final `uv run pytest tests/voice/tts/test_elevenlabs.py -v` and confirm all 7 tests are green
- Report any failures to Hari

**Deliverables:**
- `_check_quota()` method on sub-branch `feat/elevenlabs-tts/quota`
- Error handling wrapped around `_call_upstream()` on sub-branch `feat/elevenlabs-tts/errors`
- Final `adapter.py` and `schemas.py` passing `ruff` and `mypy` on sub-branch `feat/elevenlabs-tts/lint`
- Confirmation that all 7 tests pass on the integrated branch

**Dependencies:**
- Hari's skeleton (quota method stub must be in place)
- Anshul's `_call_upstream()` (error handling wraps this)

**Effort:** ~6–8 hours total  
**Suggested order:** Quota check on Day 3 (parallel with Anshul's HTTP work); error handling Day 3–4; lint pass Day 4–5 after all code is integrated

---

## 8. Dependency Graph

```
[Day 1 — Parallel, no dependencies]
  Nawaz:  Test + mock analysis → spec document
  Nawaz:  ElevenLabs API research → API contract
  Hari:   Define architectural decisions (§6.4)
  Hari:   Implement adapter skeleton + push feat/elevenlabs-tts branch

[Day 2 — After Day 1 artifacts are shared]
  Nawaz:  schemas.py (needs API contract)
  Anshul: _call_upstream() stub (needs skeleton + API contract)
  Vichitravir: Study quota test; prepare _check_quota() stub

[Day 3 — After skeleton + API contract are done]
  Anshul: _chunk_text() (needs skeleton)
  Anshul: Live API test setup
  Vichitravir: _check_quota() implementation (can run parallel to Anshul's HTTP work)

[Day 4 — After HTTP call is integrated]
  Vichitravir: Error handling (_call_upstream wrapping)
  Anshul: Live API test (needs _call_upstream working)
  Hari:   Integration pass — merge sub-branches sequentially

[Day 5 — Final quality pass]
  Vichitravir: ruff + mypy pass on integrated files
  Vichitravir: Confirm all 7 tests green
  Hari:   Final review, open PR

[Day 6–7 — Review cycle]
  Hari:   Address CODEOWNER review comments, coordinate merge
```

**Critical path:** Nawaz spec/API research → Hari skeleton → Anshul HTTP → Vichitravir errors → Vichitravir lint → all 7 tests green → PR

---

## 9. Collaboration Workflow

### Branch Strategy

```
main (upstream)
  └── feat/elevenlabs-tts          ← Team branch (Hari manages)
        ├── feat/elevenlabs-tts/schemas     ← Nawaz
        ├── feat/elevenlabs-tts/http        ← Anshul
        ├── feat/elevenlabs-tts/chunking    ← Anshul
        ├── feat/elevenlabs-tts/live        ← Anshul
        ├── feat/elevenlabs-tts/quota       ← Vichitravir
        ├── feat/elevenlabs-tts/errors      ← Vichitravir
        └── feat/elevenlabs-tts/lint        ← Vichitravir
```

### Merge Order (Hari integrates sequentially into `feat/elevenlabs-tts`)

1. `skeleton` (Hari — Day 1, initial commit to team branch)
2. `schemas` (Nawaz — Day 2)
3. `http` (Anshul — Day 3)
4. `chunking` (Anshul — Day 3)
5. `quota` (Vichitravir — Day 3–4)
6. `errors` (Vichitravir — Day 4)
7. `lint` (Vichitravir — Day 5, final pass on fully integrated file)

### Communication Rules

- **Post research artifacts in team chat the moment they are complete** — Nawaz's spec and API contract unblock everyone else.
- **Never push directly to `feat/elevenlabs-tts`** — always work on a sub-branch and PR into the team branch.
- **Hari reviews before every merge** — each sub-branch PR targets `feat/elevenlabs-tts`, not `main`.
- **Coordinate on `adapter.py` conflicts early** — Hari owns the final `synthesize()` method body and integrates all helper functions. Members implement logic as **separate methods/functions**, not inline in `synthesize()`.
- **Vichitravir runs the full test suite** after each integration merge and posts the result in team chat.

### How to Avoid Merge Conflicts

Each member works in isolation on clearly delimited units:

| Member | Works on |
|---|---|
| Hari | `synthesize()` body, `__init__`, `config` injection |
| Nawaz | `schemas.py` (entirely separate file) |
| Anshul | `_call_upstream()`, `_chunk_text()` (separate methods) |
| Vichitravir | `_check_quota()` (separate method), error wrapping inside `_call_upstream()` |

Hari wires everything together in the final integration pass.

---

## 10. Suggested Timeline (4-Person)

```
Day 1  
  ├── Hari:         Define §6.4 decisions, push adapter.py skeleton to feat/elevenlabs-tts
  ├── Nawaz:        Read + analyze all 7 tests and mock → post spec in team chat
  └── Nawaz:        Research ElevenLabs API docs → post API contract in team chat

Day 2  
  ├── Nawaz:        Implement schemas.py → open sub-branch PR → Hari reviews + merges
  ├── Anshul:       Study Nawaz's API contract; implement _call_upstream() stub
  └── Vichitravir:  Study quota test + mock attributes; plan _check_quota()

Day 3  
  ├── Anshul:       Complete _call_upstream() + _chunk_text() → open sub-branch PRs
  ├── Anshul:       Begin live API test setup
  └── Vichitravir:  Implement _check_quota() → open sub-branch PR

Day 4  
  ├── Hari:         Integration pass — merge http, chunking, quota sub-branches
  ├── Vichitravir:  Error handling in _call_upstream() wrapper → open sub-branch PR
  └── Anshul:       Live API test (needs integrated HTTP path) → open sub-branch PR

Day 5  
  ├── Hari:         Merge errors + live sub-branches; final integration
  ├── Vichitravir:  ruff check + mypy pass on all elevenlabs/ files → open lint PR
  └── Vichitravir:  Run all 7 tests → report results to Hari

Day 6  
  └── Hari:         Final review of lint PR; open implementation PR against upstream with required markers

Day 7–10  
  └── Hari:         Address CODEOWNER review comments; coordinate merge before deadline
```

---

## 11. Running Tests

```bash
# Install dependencies
uv sync

# Run the 7 ElevenLabs tests (no credentials needed — uses mock)
uv run pytest tests/voice/tts/test_elevenlabs.py -v

# Run with coverage
uv run pytest tests/voice/tts/test_elevenlabs.py -v --cov=glc/voice/tts/providers/elevenlabs

# Run the live API test (requires ELEVENLABS_API_KEY set in env)
uv run pytest tests/voice/tts/ -v -m requires_live_api

# Lint check
uv run ruff check glc/voice/tts/providers/elevenlabs/

# Type check
uv run mypy glc/voice/tts/providers/elevenlabs/

# CI skips live API tests — it runs:
uv run pytest tests/voice/tts/test_elevenlabs.py -m "not requires_live_api" -v
```

### The 7 Tests That Must Pass

| Test | What It Checks |
|---|---|
| `test_provider_name_matches` | `Provider.name == "elevenlabs"` |
| `test_synthesize_returns_synthesize_result` | Returns `SynthesizeResult` with `provider="elevenlabs"`, non-empty `audio_b64`, `sample_rate > 0` |
| `test_synthesize_passes_text_to_upstream` | `received_calls[-1]["text_len"] == len(input_text)` |
| `test_synthesize_records_sample_rate` | `result.sample_rate == mock.canned_sample_rate` |
| `test_synthesize_propagates_upstream_error` | `TTSError` raised with `status == 502` when mock injects `upstream_failure = (502, ...)` |
| `test_synthesize_handles_empty_text` | Returns `SynthesizeResult` for `text=""`, does not raise |
| `test_channel_specific_behaviour_free_tier_quota_tracking` | `TTSError(status=429)` raised before sending when `chars_used + len(text) > chars_limit`; message contains "quota" or "limit" |

---

## 12. Risks and Recommendations

| Risk | Likelihood | Owner | Mitigation |
|---|---|---|---|
| **Merge conflicts in `adapter.py`** | High | Hari | Each member works on separate methods. Hari is the sole integrator of `synthesize()`. Never commit logic inline in `synthesize()` — always extract to a named method. |
| **Boundary CI rejection** | Medium | All | Never touch files outside `glc/voice/tts/providers/elevenlabs/`. |
| **Mock vs. real path confusion** | Medium | Hari + Vichitravir | The mock delegation check is the **first thing** in `synthesize()`. Quota check runs before delegation for the mock path; `_call_upstream()` is never reached in mock mode. |
| **Quota `text_len` mismatch** | Medium | Anshul + Vichitravir | Quota is checked against total `len(text)` before chunking. `received_calls` records total `len(text)`. These must be consistent — coordinate between Anshul (chunking) and Vichitravir (quota). |
| **ElevenLabs response format** | Medium | Anshul | README confirms raw MP3 bytes. Convert with `base64.b64encode(response.content).decode("ascii")`. Nawaz to confirm from API docs. |
| **Empty text edge case** | Low | Vichitravir | Implement a short-circuit guard: `if not text: return SynthesizeResult(audio_b64="", ...)`. This must run before quota check to avoid counting 0 chars. |
| **`ruff B` rules on async** | Low | Vichitravir | `B` rules forbid bare `except:`, shadowing builtins, etc. Run `ruff check --select B` in isolation to catch these before the final pass. |
| **`httpx` availability** | None | — | `httpx>=0.27` is already in `pyproject.toml` — no changes needed. |
| **PR open too late** | Low | Hari | PR should be open by Day 6 (2026-06-30) to allow CODEOWNER review time before the 2026-07-05 deadline. `@theschoolofai` CODEOWNER review is required — you cannot self-merge. |
| **Live API key unavailable** | Low | Anshul | Free tier accounts are instant. If the key cannot be obtained, mark the live test with a skip reason and proceed — CI skips `requires_live_api` tests anyway. |

### Final Checklist Before Opening PR

- [ ] All 7 tests in `tests/voice/tts/test_elevenlabs.py` pass (`uv run pytest tests/voice/tts/test_elevenlabs.py -v`)
- [ ] `ruff check glc/voice/tts/providers/elevenlabs/` — zero violations
- [ ] `mypy glc/voice/tts/providers/elevenlabs/` — zero errors
- [ ] No files outside `glc/voice/tts/providers/elevenlabs/` are modified
- [ ] PR description contains `# Group: Group ElevenLabs` and `# Slot: elevenlabs`
- [ ] `test_live_synthesize` is marked `@pytest.mark.requires_live_api`
- [ ] CI boundary check, test-changed-slot, and scorecard workflows all pass
