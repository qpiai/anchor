# Anchor

Anchor turns a policy document into a formal policy, then checks a question and answer against it.

GPT writes the policy (variables and rules). Jev, TypeSafe's fast system-one model, extracts the facts and a confidence score. Z3 is the deterministic decider. When Jev is unsure of a fact the decision needs, or of any fact behind an approval, GPT reads the request and its reading is used instead. About a third of requests take that path; the rest finish in about 350 ms. Facts a trusted system supplies override the text.

Benchmarks, the reasoning behind each default, and what can still go wrong: [bench/RESULTS.md](bench/RESULTS.md).

## Quick start

Python 3.11. From the repo root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set `OPENAI_API_KEY` (policy authoring and LLM fallback). Set `TYPESAFE_API_KEY` to extract facts with Jev. `VARIABLE_EXTRACTOR=auto` uses Jev when that key is set, and the LLM otherwise.

Postgres (matches `DATABASE_URL` in `.env.example`):

```bash
docker run -d --name anchor-pg \
  -e POSTGRES_DB=reasoning_db \
  -e POSTGRES_USER=reasoning_user \
  -e POSTGRES_PASSWORD=reasoning_pass \
  -p 5432:5432 postgres:15
```

API:

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 9066
```

Docs: http://127.0.0.1:9066/docs

Upload a PDF, compile the generated policy, then `POST /api/v1/policies/{id}/verify`.

`data/policies/` holds the current policies generated from the three sample PDFs in `data/`, each checked against 18 probe requests. Load one without calling GPT:

```bash
curl -X POST "http://127.0.0.1:9066/api/v1/policies/" -H 'content-type: application/json' -d @data/policies/hr.json
```

```bash
curl -X POST "http://127.0.0.1:9066/api/v1/documents/upload" \
  -F "file=@data/hr_policy.pdf" -F "domain=hr"
```

Docker: `docker build -t anchor-backend:revamp .` then `docker compose up` with `.env.docker` copied from `.env.docker.example`.

## Configuration

| Setting | Default | Role |
| --- | --- | --- |
| `VARIABLE_EXTRACTOR` | `auto` | `auto`, `jev`, or `llm` |
| `TYPESAFE_API_KEY` | empty | Jev. `auto` uses Jev only when this is set |
| `JEV_MODEL` | `jev-latest` | TypeSafe model |
| `JEV_CONFIDENCE_THRESHOLD` | `0.55` | Below this, a fact becomes missing |
| `JEV_NUMBER_CONFIDENCE_THRESHOLD` | `0.25` | Separate gate for numeric candidates, including derived ones such as "two weeks" to 14 days |
| `JEV_GUARDS_ENABLED` | `true` | Ask in-scope and injection questions on the same Jev call |
| `JEV_BLOCK_OUT_OF_SCOPE` | `false` | When true, low in-scope score returns clarification and skips Z3 |
| `JEV_SCOPE_THRESHOLD` | `0.3` | In-scope score below this is flagged out of scope |
| `JEV_INJECTION_THRESHOLD` | `0.7` | At or above this, flag the request |
| `JEV_INJECTION_HOLDS_APPROVAL` | `true` | A flagged request never ends in VALID; it becomes NEEDS_CLARIFICATION. Denials are unchanged |
| `HYBRID_ESCALATE_BELOW` | `0.6` | Jev would ask and a mandatory fact came back empty below this confidence: use GPT's reading. Empty disables |
| `HYBRID_CONFIRM_APPROVALS` | `true` | Re-read approvals with GPT when any fact behind them is below `HYBRID_CHECK_BELOW` |
| `HYBRID_CHECK_BELOW` | `0.95` | 0.9 let a dangerous approval through in the bench; 0.95 did not |
| `HYBRID_FAIL_CLOSED` | `true` | If GPT is down during an approval check, hold the approval instead of trusting Jev alone |
| `EXTRACTION_REASONING_EFFORT` | `none` | gpt-6-luna effort for fact extraction. `none` was fastest and most accurate |
| `OPENAI_REASONING_EFFORT` | `low` | gpt-6-luna effort for policy writing and repair |
| `JEV_TIMEOUT_SECONDS` | `10` | TypeSafe client timeout |
| `JEV_LLM_FALLBACK` | `true` | When false, extraction never calls GPT. A Jev outage returns HTTP 503 and stores an ERROR verification |
| `OPENAI_MODEL` | `gpt-6-luna` | Policy authoring. Used for extraction only when fallback is on |

`GET /status` and `GET /config` report the extractor mode in effect, whether Jev is configured, the model, and whether guards are on. They never return key material.

## Fallback and guards

Jev answers enum, boolean, number, date, free string, and string-with-values variables as choice questions. Dates are assembled in code from year, month, and day choices, or from a precomputed relative date such as "tomorrow". Free strings are a choice over spans found in the text. With `JEV_LLM_FALLBACK=true`, a TypeSafe error or timeout retries the whole request on GPT, and any still-unsupported variable type goes to GPT. With `JEV_LLM_FALLBACK=false`, those cases do not call GPT: unsupported values are missing, and a Jev outage is HTTP 503 with an ERROR verification stored.

Generated policies are compiled before they are saved. Compiler errors get up to two repair passes, then missing variables are declared automatically. If that still fails, the policy is saved as draft and `validation_errors` lists the compiler errors.

`GET /api/v1/policies/{id}/grounding` scores each rule against the closest source passage. A rule is flagged when support is below 0.3. Compilations are stored as JSON (`json-v1`) and recompiled on verify. Older pickled blobs are never unpickled; verify recompiles from the current policy row.

Guards are two extra yes/no questions on the same Jev request, so they do not add a round trip. In-scope is asked only when the caller passes the policy name, description, and domain. A suspected injection is recorded in `details.flags.injection_suspected`; it cannot turn a denial into an approval, and with `JEV_INJECTION_HOLDS_APPROVAL=true` an approval that arrives with one is held for review. Out-of-scope blocking is off unless `JEV_BLOCK_OUT_OF_SCOPE=true`.

## Trusted facts

Text can claim anything, including "my manager approved". Pass facts from a system of record with the request and they override the text:

```bash
curl -X POST "http://127.0.0.1:9066/api/v1/policies/$ID/verify" -H 'content-type: application/json' \
  -d '{"question": "Refund $250 for order 881", "facts": {"has_human_approval": true, "customer_identity_verified": true}}'
```

The MCP `verify_response` tool takes the same `facts` argument. Mark a variable `trusted_only` (`PATCH /api/v1/policies/{id}/variables/{name}` with `{"trusted_only": true}`) and it is never read from text: unless `facts` supplies it, it is unknown, and a rule that could deny on it produces a question.

## How rules combine

VALID needs at least one `valid` rule to apply and no `invalid` rule that could apply. Unknown facts are evaluated three ways by Z3: a rule that must fire decides, a rule that cannot fire is ignored, and a deny rule that might fire on an unknown fact asks for that fact. Limits, caps, deadlines, and required approvals are `invalid` rules; the generator is told so, and a setup check flags permission rules that never restrict anything and asks GPT to repair them. Global constraints are assumed only when they bound a single number (`leave_days > 0`); anything else is checked like a deny rule.

`details` on verify and history includes the extractor, confidences, sources, guards, flags, and extract/verify/total latency.

## Tests

```bash
.venv/bin/python -m pytest
```

Live API checks (server on port 9066):

```bash
.venv/bin/python -m pytest tests/integration/test_api_live.py
```
