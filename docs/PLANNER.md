# Aegis AI — Day-wise Planner

**Sprint:** Day 1 (Nov 17, 2026) → Day 15 (Dec 1, 2026)
**Last updated:** Nov 17, 2026
**Tracker:** [GitHub milestones](https://github.com/isayan58/aegis-agentic-ai/milestones) · [Issues](https://github.com/isayan58/aegis-agentic-ai/issues). Each `#NN` below is a GitHub issue.
**Design:** general-purpose research assistant. Aegis takes a research request (research, compare or rank), asks for clarification when the request is incomplete, collects sourced evidence, verifies it, asks a human for approval, and returns a cited report. The design works for any subject: football players, data platforms or anything else.

- **Days 1–10:** v1. Orchestration, tools, verification, human approval, persistence, evals, deployment.
- **Days 11–15:** v2. RAG and MCP.

### Status key

| Mark | Meaning |
|---|---|
| ✅ | Done |
| 🟡 | In progress |
| ⬜ | Not started |
| 🔁 | Carried over from an earlier day |

### How each step is written

Each open step in Days 1–10 is one GitHub issue, with:
- **Goal:** what the step achieves
- **Estimate:** rough time
- **Tasks:** small checkboxes, about 15–30 min each
- **Files:** where the code goes
- **Done when:** the check that proves the step is finished

---

## Overview

| Day | Date | Theme | Status |
|---|---|---|---|
| 1 | Nov 17 | Foundation, model gateway, cost control | 🟡 Mostly done (5 items carried over) |
| 2 | Nov 18 | Schemas, clarification, state, tools, first evals | 🟡 Steps 1–3 done; 4–6 left |
| 3 | Nov 19 | Report schema, single-agent baseline, planner | ⬜ |
| 4 | Nov 20 | Worker subgraphs and controlled web research | ⬜ |
| 5 | Nov 21 | Verifier, retries, human approval, persistence | ⬜ |
| 6 | Nov 22 | Full graph, streaming API | ⬜ |
| 7 | Nov 23 | Frontend, containers, CI, Azure deployment (**MVP live**) | ⬜ |
| 8 | Nov 24 | Security and Execution Explorer | ⬜ |
| 9 | Nov 25 | Full A/B/C evaluation on 100 cases | ⬜ |
| 10 | Nov 26 | Docs, demo, **v1.0.0 release** | ⬜ |
| 11 | Nov 27 | RAG 1: document ingestion and vector store | ⬜ |
| 12 | Nov 28 | RAG 2: retrieval quality and retrieval evals | ⬜ |
| 13 | Nov 29 | RAG 3: RAG in the graph, grounding and RAG evals | ⬜ |
| 14 | Nov 30 | MCP 1: Aegis MCP server and MCP client | ⬜ |
| 15 | Dec 1 | MCP 2: security, evals, deployment, **v2.0.0 release** | ⬜ |

---

## Backlog (carried over, do before Day 3)

| From | Issue | Item | Status |
|---|---|---|---|
| Day 1 | #9 | Cost calculation | ⬜ |
| Day 1 | #10 | Budget enforcement | ⬜ |
| Day 1 | #11 | Choose the model by role | ⬜ |
| Day 1 | #12 | Automatic usage tracking | ⬜ |
| Day 1 | #13 | Bad-credential handling | ⬜ |
| Day 2 | #20 | Notebook 01 cleanup | ⬜ |
| Day 2 | #21 | Move notebook checks into tests | ⬜ |

Suggested order: #20 → #21 → #9 → #10 → #11 → #12 → #13. Cost calculation comes before the budget, and the budget comes before automatic tracking.

---

## Day 1 — Nov 17 — Foundation, model gateway, cost control
**Status:** 🟡 Mostly done
**Deliverable:** a FastAPI backend that calls Foundry and OpenAI through one interface, with costs tracked.
**Gate:** live tests pass; no secrets in logs or Git.

**Done:** #1 uv project and config files · #2 package layout · #3 settings with `SecretStr` · #4 gateway for OpenAI and Foundry · #5 usage extraction · #6 `/health` and `/ready` · #7 offline and live tests · #8 notebook 00

### #9 · 🔁 Cost calculation
**Goal:** turn the token usage from every call into an exact USD cost.
**Estimate:** ~45 min
- [ ] Create `src/aegis/llm/pricing.py` with a frozen `ModelPrice` dataclass: input, cached input and output price per 1M tokens
- [ ] Use `Decimal` for all money values, not `float`
- [ ] Fill in prices for `gpt-5.4` and `gpt-5-mini` from the official pricing page, with a comment giving the date you checked
- [ ] `get_price(model)` raises `UnknownModelPriceError` for a model that isn't in the table (never return $0)
- [ ] `calculate_cost(usage)`: uncached input = input − cached; bill cached tokens at the cached rate
- [ ] Don't add reasoning tokens again; they're already counted in output tokens
- [ ] Cap cached tokens at the input token count, in case a provider reports odd numbers
- [ ] Test: 1M input + 1M output on `gpt-5.4` = exactly $17.50
- [ ] Test: a small call (1,000 in / 500 out) gives the exact expected cost
- [ ] Test: cached tokens are billed at the cheaper rate
- [ ] Test: an unknown model raises an error

**Files:** `src/aegis/llm/pricing.py`, `tests/test_pricing.py`
**Done when:** the tests pass, and the cost of one live call matches your own calculation by hand.

### #10 · 🔁 Budget enforcement
**Goal:** stop a run from spending more than its cap.
**Estimate:** ~1 h
- [ ] Add `budget_limit_usd: Decimal` (must be > 0) to `Settings`, and `BUDGET_LIMIT_USD` to `.env.example`
- [ ] Create `BudgetExceededError`
- [ ] Create a `CallRecord` dataclass: provider, model, input, cached, output and reasoning tokens, cost
- [ ] `BudgetTracker(limit)` with `spent_usd`, `remaining_usd` (never negative) and `calls`
- [ ] `check()` raises `BudgetExceededError` once spent ≥ limit
- [ ] `record(usage)` calculates the cost, stores a `CallRecord` and adds to the total
- [ ] Protect the total with a `threading.Lock`, because parallel workers will share one tracker
- [ ] Log one line per call with metadata only (model, tokens, cost, total). Never log prompts or keys.
- [ ] Log a warning when the budget runs out
- [ ] Tests: costs add up; a call after the cap is blocked; hitting the cap exactly blocks the next call
- [ ] Test: 8 threads × 50 records lose no updates
- [ ] Test: a prompt passed in the usage dict never appears in the logs

**Files:** `src/aegis/llm/budget.py`, `src/aegis/config.py`, `tests/test_budget.py`
**Done when:** the tests pass, and in the notebook a tracker with a $0.0001 cap blocks the second live call.

### #11 · 🔁 Choose the model by role
**Goal:** graph nodes ask for a role, and config decides the provider and model.
**Estimate:** ~1 h
- [ ] Define `Role = Literal["planner", "researcher", "analyst", "judge", "reporter"]`
- [ ] Create a `RoleModel` schema: provider, model, `max_completion_tokens`, `reasoning_effort`
- [ ] Add a role → `RoleModel` mapping to settings, with defaults you can override from `.env`
- [ ] Defaults: planner, judge and reporter on OpenAI `gpt-5.4`; researcher and analyst on Foundry `gpt-5-mini`
- [ ] Move model construction into a private `_build_model(provider, model, params)`
- [ ] Change the public function to `get_model(role)`
- [ ] Use `max_completion_tokens` and `reasoning_effort` on the OpenAI path too (`gpt-5.4` is a reasoning model)
- [ ] At startup, fail if any role's model is missing from the price table
- [ ] At startup, warn if `judge` uses the same provider as `researcher`
- [ ] Update `test_gateway.py`: each role resolves to its configured provider and model
- [ ] Update the live smoke test to call each distinct provider/model pair once

**Files:** `src/aegis/llm/gateway.py`, `src/aegis/config.py`, `tests/test_gateway.py`, `tests/test_smoke_live.py`
**Done when:** `get_model("judge")` and `get_model("researcher")` return different providers, and all tests pass.

### #12 · 🔁 Automatic usage tracking
**Goal:** every LLM call in a run is checked and recorded, with no code in each node.
**Estimate:** ~1 h
- [ ] Create `BudgetCallbackHandler(BaseCallbackHandler)` that holds a `BudgetTracker`
- [ ] Set `raise_error = True` on the handler. Without it, LangChain swallows the `BudgetExceededError`.
- [ ] Have the gateway attach metadata to each model: `aegis_role`, `aegis_provider`, `aegis_model`
- [ ] `on_chat_model_start`: call `tracker.check()` and store provider and model by `run_id`
- [ ] `on_llm_end`: read `usage_metadata` from the generated message and call `tracker.record()`
- [ ] Add a helper, `new_run_budget(settings)`, that returns the tracker plus a `callbacks` config to pass to `invoke`
- [ ] Test with a fake chat model whose messages include `usage_metadata`: each call is recorded
- [ ] Test: once the tracker is over the cap, `invoke` raises `BudgetExceededError`
- [ ] Notebook: two live calls with the handler; print `tracker.calls`

**Files:** `src/aegis/llm/callbacks.py`, `src/aegis/llm/gateway.py`, `tests/test_callbacks.py`
**Done when:** a call made through `get_model(role)` with the callbacks config shows up in `tracker.calls` with no extra code.

### #13 · 🔁 Bad-credential handling
**Goal:** a misconfigured provider fails clearly and never leaks secrets.
**Estimate:** ~45 min
- [ ] In the notebook, call OpenAI with a wrong key and note the exception type
- [ ] Call Foundry with a wrong deployment name and note the exception type
- [ ] Call with an unreachable base URL and note the exception type
- [ ] Create Aegis error types: `ProviderAuthError`, `ProviderNotFoundError`, `ProviderUnavailableError`
- [ ] Wrap provider exceptions into these types in the gateway. Keep the provider name; drop the raw text.
- [ ] Live tests (auth failures cost nothing): each misconfiguration raises the right Aegis error
- [ ] Assert that the key never appears in `str(exc)`, `repr(exc)` or the captured logs
- [ ] Confirm `/ready` checks config only and never calls a provider

**Files:** `src/aegis/llm/errors.py`, `src/aegis/llm/gateway.py`, `tests/test_provider_errors_live.py`
**Done when:** all three misconfigurations raise the right Aegis error, and no secret appears in any output.

---

## Day 2 — Nov 18 — Schemas, clarification, state, tools, first evals
**Status:** 🟡 Steps 1–3 done
**Deliverable:** reusable schemas, working clarification checks, safe merging of parallel results, tested tools, a runnable eval suite.
**Gate:** reducer tests pass, tool tests pass, 15 eval cases load and run.

**Done:** #14 Step 1: request schemas · #15 Step 2: clarification · #16 Step 3: evidence schemas, moved into modules

### #17 · Step 4: Graph state and reducers
**Goal:** parallel workers combine their results without conflicts, lost data or duplicates on retry.
**Estimate:** ~2 h
- [ ] In the notebook, write a table of state keys: owner node, type, reducer
- [ ] Add a `RunStatus` enum: `running`, `needs_clarification`, `awaiting_approval`, `completed`, `rejected`, `degraded`, `failed`, `budget_exceeded`
- [ ] Store `sources`, `evidence` and `findings` as dicts keyed by ID, not as lists
- [ ] Make evidence IDs deterministic, e.g. a hash of `source_id` + `locator`, so a retry produces the same ID
- [ ] Write a `merge_by_id` reducer: merges dicts, and a later write replaces the same ID
- [ ] Write the other reducers: `append` for `errors` and `node_events`, `sum_usage` for `usage`
- [ ] Define `AegisState` (TypedDict): `request`, `clarification`, `plan`, `sources`, `evidence`, `findings`, `calculations`, `verification`, `approval`, `report`, `status`, `retry_count`, `usage`, `errors`, `node_events`
- [ ] Toy graph: START → `worker_a` and `worker_b` in parallel → `join` → END
- [ ] Experiment 1: no reducer → see `InvalidUpdateError`, and write down why it happens
- [ ] Experiment 2: with `merge_by_id` → both workers' evidence is present
- [ ] Experiment 3: rerun `worker_a` with changed content and the same IDs → replaced, not duplicated
- [ ] Write `bundle_from_state(state)`, which builds a `ResearchBundle` and so runs your reference checks
- [ ] Move the code into `state.py` and `reducers.py`

**Files:** `src/aegis/state.py`, `src/aegis/reducers.py`, `tests/test_state.py`, notebook `01_schemas_and_state`
**Done when:** the tests cover a merge, a retry overwrite and a broken reference, and they pass.

### #18 · Step 5: Tools and sample evidence
**Goal:** reliable local evidence, and deterministic calculations that agents can call.
**Estimate:** ~2.5 h
- [ ] `data/fixtures/football_demo_v1.json`: 3 fictional players, 2 seasons each: matches, minutes, goals, assists, key passes, competition
- [ ] `data/fixtures/platforms_demo_v1.json`: 3 fictional vendors: storage $/TB-month, compute $/h, certifications, SLA, regions
- [ ] Each fixture has a header: title, `dataset_ref`, `is_test_data: true`
- [ ] `load_fixture(dataset_ref)` validates the file with Pydantic
- [ ] Map each factor to fixture fields (e.g. "Scoring" → goals, minutes)
- [ ] `lookup_evidence(subject, factor, dataset_ref)` returns a `SourceRecord` and its `EvidenceItem`s, with deterministic IDs
- [ ] An unknown subject or factor returns an empty result with a reason. It doesn't raise, so the agent can report the gap.
- [ ] `per_90(value, minutes)`: rejects minutes ≤ 0
- [ ] `normalize(values, direction)`: higher-is-better or lower-is-better; returns a fixed score when every value is equal
- [ ] `weighted_score(scores, weights)`: weights must add up to 1 (with a tolerance)
- [ ] `rank(scores)`: handles ties consistently
- [ ] `sensitivity_check(scores, weights)`: moves each weight ±10%, re-normalizes, and reports whether the winner changes
- [ ] `calculator(expression)`: parses with `ast`, allows only numbers and + − × ÷ ( ). Never use `eval`.
- [ ] Wrap each function with `@tool`, with a clear docstring and typed arguments
- [ ] Tests for each function, including edge cases: zero minutes, all-equal values, bad weights, `__import__('os')` passed to the calculator

**Files:** `data/fixtures/`, `src/aegis/tools/evidence.py`, `src/aegis/tools/calculators.py`, `tests/test_tools.py`, notebook `02_tools`
**Done when:** every tool has tests, the calculator rejects code injection, and the lookup output passes `ResearchBundle` validation.

### #19 · Step 6: The first 15 eval cases
**Goal:** a repeatable eval suite from Day 2 onwards.
**Estimate:** ~1.5 h
- [ ] Define an `EvalCase` schema: `id`, `category`, `input`, `expected` (clarification fields, rejection text, tool outputs)
- [ ] Write `evals/datasets/v1.jsonl` with 15 cases
- [ ] 6 valid requests: 3 football, 3 platforms; mix of research, compare and rank
- [ ] 4 that need clarification: missing factors, missing time period, missing coverage, rank without a ranking basis
- [ ] 3 invalid: one subject for compare, duplicate subjects, empty objective
- [ ] 2 reference-integrity cases: unknown source, unknown evidence
- [ ] Work out 3 expected tool outputs by hand in a spreadsheet and copy them into the cases
- [ ] `evals/runner.py`: load the cases, run deterministic checks, print a pass/fail table
- [ ] Save each run to `evals/results/<timestamp>.json`
- [ ] Add a pytest test that checks every case in the dataset is valid
- [ ] Notebook `09_eval_lab`: run the suite and show the results

**Files:** `evals/datasets/v1.jsonl`, `evals/runner.py`, `evals/results/`, `tests/test_eval_dataset.py`, notebook `09_eval_lab`
**Done when:** 15 out of 15 pass, or every failure has a known cause.

### #20 · 🔁 Notebook 01 cleanup
**Goal:** the notebook shows only what it adds, and imports everything else.
**Estimate:** ~15 min
- [ ] Remove the cells that are commented-out copies of code now in `src/`
- [ ] Remove the local `NonEmptyText` definition and the unused pydantic imports
- [ ] Import `check_clarity` once only
- [ ] Delete empty cells
- [ ] Restart & Run All, then save so the stored outputs match the code
- [ ] Commit

**Files:** `notebooks/01_schemas_and_state.ipynb`
**Done when:** execution counts run 1, 2, 3… in order and all three `PASS` lines print.

### #21 · 🔁 Move notebook checks into tests
**Goal:** `pytest` catches schema and clarification regressions, not just the notebook.
**Estimate:** ~45 min
- [ ] `tests/test_schemas.py`: a valid football request and a valid platform request are accepted
- [ ] Rejected: compare with one subject; duplicate subjects (case-insensitive); duplicate factors
- [ ] Rejected: unknown fields (`extra="forbid"`)
- [ ] `SourceRecord`: a web source needs a URL; a dataset source needs a `dataset_ref`
- [ ] `ResearchBundle`: unknown source, unknown evidence, duplicate IDs, repeated evidence IDs are all rejected
- [ ] `tests/test_clarification.py`: an incomplete request gets questions about factors, time period and coverage
- [ ] A fully specified compare request gets no questions
- [ ] Rank without `ranking_basis` gets exactly one question

**Files:** `tests/test_schemas.py`, `tests/test_clarification.py`
**Done when:** `uv run pytest` passes with the new tests.

---

## Day 3 — Nov 19 — Report schema, single-agent baseline, planner
**Status:** ⬜
**Deliverable:** Experiment A (single agent) runs end to end; the planner produces a valid plan.
**Gate:** the baseline answers a request with tool calls; the planner routes correctly on the eval cases.

### #22 · Step 1: Report schema
**Goal:** one output format shared by every architecture, so A, B and C can be compared.
**Estimate:** ~45 min
- [ ] `ComparisonRow`: subject, factor, value, unit, `evidence_ids`
- [ ] `RankingEntry`: position, subject, score, `evidence_ids`
- [ ] `FinalReport`: summary, mode, subjects, comparison rows, ranking (rank mode only), findings, limitations, citations, status
- [ ] Validator: ranking is required in rank mode and not allowed otherwise
- [ ] `validate_report_against_bundle(report, bundle)`: every cited ID exists in the bundle
- [ ] Tests: a valid report passes; a citation to unknown evidence fails; rank mode without a ranking fails

**Files:** `src/aegis/schemas.py`, `tests/test_report.py`
**Done when:** the tests pass, and a hand-written football report validates against the Day 2 fixture bundle.

### #23 · Step 2: Single-agent baseline (Experiment A)
**Goal:** the simplest working agent, as the benchmark that B and C must beat.
**Estimate:** ~1.5 h
- [ ] Write the system prompt: use tools for every number, cite `source_id`s, say clearly when evidence is missing, never invent statistics
- [ ] `create_agent(model=get_model("researcher"), tools=[...], response_format=FinalReport)`
- [ ] Run the football compare request; read the message history and list the tool calls in order
- [ ] Run the platform rank request; check the ranking against your spreadsheet
- [ ] Attach the budget callbacks and print the cost of each run
- [ ] Check the output with `validate_report_against_bundle`
- [ ] Wrap it as `run_baseline(request) -> FinalReport`
- [ ] Add a live test (`@pytest.mark.live`) for one request, with a small budget cap

**Files:** `src/aegis/graphs/baseline.py`, `tests/test_baseline_live.py`, notebook `03_single_agent_baseline`
**Done when:** both demo requests return a valid, cited report, and you know the cost and number of tool calls for each.

### #24 · Step 3: Planner
**Goal:** turn a clear request into a validated plan of worker steps.
**Estimate:** ~1.5 h
- [ ] `PlanStep`: `step_id` (e.g. `evidence:messi:scoring`), `worker` (`evidence` / `web` / `analysis`), subject, factor, `depends_on`
- [ ] `ResearchPlan`: steps and a rationale
- [ ] Validators: every subject × factor pair is covered; analysis steps depend on evidence steps; no cycles; unique IDs
- [ ] `plan_deterministically(request)`: a plan built in code, with no LLM. Use it in tests and as a fallback.
- [ ] LLM planner: `get_model("planner").with_structured_output(ResearchPlan)`
- [ ] Compare the LLM plan with the deterministic plan on the 6 valid eval cases
- [ ] Decide when the LLM planner is worth it, e.g. choosing between dataset and web per factor, and write the reason down

**Files:** `src/aegis/nodes/planner.py`, `tests/test_planner.py`, notebook `04_planner_and_fanout`
**Done when:** both planners produce valid plans for all valid eval cases, and the tests use the deterministic one.

### #25 · Step 4: Fan-out and routing
**Goal:** the first real graph: validate → clarify → plan → parallel workers.
**Estimate:** ~1.5 h
- [ ] `validate_input` node: parse into a `ResearchRequest`; on failure set `status=failed` with a safe message
- [ ] `clarify` node: run `check_clarity()`; if questions are needed, set `status=needs_clarification` and end. The interrupt comes on Day 5.
- [ ] `planner` node writes `plan`
- [ ] `route_to_workers(state)` returns one `Send` per evidence step
- [ ] Stub worker that returns fixed evidence, so the graph runs before Day 4
- [ ] `collect` node after the workers
- [ ] Write every router as a pure function and unit-test it separately
- [ ] Draw the graph (Mermaid) and save the picture in `docs/`
- [ ] Run 3 subjects × 2 factors and confirm 6 workers run

**Files:** `src/aegis/graphs/routing.py`, `src/aegis/nodes/`, `tests/test_routing.py`
**Done when:** the valid, needs-clarification and invalid inputs each take the right path in the tests.

### #26 · Step 5: Evals to 30 cases
**Goal:** measure routing and tool use, not just final answers.
**Estimate:** ~1 h
- [ ] Add 15 cases with expected workers and expected tool sequences
- [ ] Evaluator: routing accuracy (expected vs actual steps in the plan)
- [ ] Evaluator: tool precision and recall (expected vs actual tool calls)
- [ ] Run the baseline on 5 cases live, with a total budget cap
- [ ] Save the results and note the 3 most common problems

**Files:** `evals/datasets/v1.jsonl`, `evals/evaluators.py`
**Done when:** 30 cases run, and routing accuracy is reported for the planner.

---

## Day 4 — Nov 20 — Worker subgraphs and controlled web research
**Status:** ⬜
**Deliverable:** the research and analysis workers run in parallel and merge cleanly.
**Gate:** parallel runs produce no duplicates and no lost evidence.

### #27 · Step 1: Evidence worker (datasets)
**Goal:** collect dataset evidence for one subject × factor.
**Estimate:** ~45 min
- [ ] Define the worker's input: subject, factor, `dataset_ref`, `step_id`
- [ ] Decide whether it needs an LLM. A dataset lookup can be plain code; write down your choice and the reason.
- [ ] Call `lookup_evidence`; return only `sources`, `evidence` and a `node_events` entry
- [ ] Missing data adds a limitation, not an error
- [ ] Test: the worker's output merges cleanly into `AegisState`

**Files:** `src/aegis/agents/evidence_worker.py`, `tests/test_evidence_worker.py`
**Done when:** the worker replaces the Day 3 stub and the routing tests still pass.

### #28 · Step 2: Controlled web research worker
**Goal:** fetch evidence from approved websites only, safely and reproducibly.
**Estimate:** ~2.5 h
- [ ] Settings: `web_research_enabled` (default false) and `web_allowed_domains`
- [ ] `fetch_page(url)`: allowed domains only, HTTPS only, 10 s timeout, 1 MB size limit, HTML content only
- [ ] Convert HTML to clean text and keep the page title
- [ ] Cache fetched pages on disk by URL hash, so evals can replay them offline
- [ ] Create a `SourceRecord` with `kind="web"`, `url` and `retrieved_at`
- [ ] Extract evidence with the `researcher` model (structured output): each excerpt must quote the page text
- [ ] Check in code that each excerpt really appears in the page text; drop any that don't
- [ ] In the prompt, mark page text as data and tell the model to ignore instructions inside it
- [ ] Tests with saved HTML files: a domain not on the list is blocked, an oversized page is rejected, an invented excerpt is dropped
- [ ] Test: with the flag off, the planner never routes to this worker

**Files:** `src/aegis/tools/web.py`, `src/aegis/agents/web_worker.py`, `tests/fixtures/html/`, `tests/test_web_worker.py`
**Done when:** the worker returns verified excerpts from an allowed page, and every blocked case is tested.

### #29 · Step 3: Analysis worker
**Goal:** turn evidence into findings, with all numbers calculated by tools.
**Estimate:** ~2 h
- [ ] Input: the merged bundle plus the request
- [ ] Calculate the derived numbers in code (`per_90`, `normalize`, `weighted_score`) and store them in `calculations` with their inputs
- [ ] `analyst` model writes `ResearchFinding`s that reference the calculations and `evidence_ids`
- [ ] Set `claim_type`: `reported_fact` for a figure taken from a source, `interpretation` for a judgement
- [ ] Rank mode: compute the ranking and the sensitivity check
- [ ] Test with a fixed bundle and a fake model: findings cite only existing evidence
- [ ] Test: the ranking matches your spreadsheet

**Files:** `src/aegis/agents/analysis_worker.py`, `tests/test_analysis_worker.py`
**Done when:** the platform rank request produces the hand-checked ranking, and every finding cites evidence.

### #30 · Step 4: Parallel run
**Goal:** prove that the workers run in parallel and merge correctly.
**Estimate:** ~1 h
- [ ] Connect evidence workers → collect → analysis in the graph
- [ ] Run 3 subjects × 2 factors
- [ ] Check that `bundle_from_state` validates after the merge
- [ ] Time the parallel run and a sequential run; record both
- [ ] Rerun one worker (simulated retry): no duplicates
- [ ] Move the code to `src/aegis/agents/`

**Files:** `src/aegis/graphs/routing.py`, notebook `05_worker_subgraphs`
**Done when:** the parallel run is faster than the sequential run and gives an identical bundle.

### #31 · Step 5: Worker tests
**Goal:** lock in the worker behaviour before adding verification.
**Estimate:** ~45 min
- [ ] Merge: 6 workers produce 6 sets of evidence, none lost
- [ ] Retry: same IDs → replaced, not duplicated
- [ ] Partial failure: one worker raises → its error is recorded and the others still merge
- [ ] Offline mode: with the web flag off, no network calls are made (patch the HTTP client to fail)

**Files:** `tests/test_parallel_workers.py`
**Done when:** all four scenarios are tested and pass offline.

---

## Day 5 — Nov 21 — Verifier, retries, human approval, persistence
**Status:** ⬜
**Deliverable:** bad results are caught and retried; a human approves before the report is final; a run survives a restart.
**Gate:** the retry loop is bounded; an approval works after a kernel restart.

### #32 · Step 1: Verifier checks
**Goal:** independent checks that catch wrong numbers and unsupported claims.
**Estimate:** ~2 h
- [ ] `CheckResult` schema: name, passed, details, `failed_step_ids`
- [ ] `VerificationReport` schema: passed, checks, feedback
- [ ] Integrity check: build the `ResearchBundle` and catch validation errors
- [ ] Numbers check: recompute every value in `calculations` from its inputs
- [ ] Citation check: every finding and report row cites evidence
- [ ] Excerpt check: every excerpt really appears in its source text
- [ ] Scope check: evidence matches the requested time period and coverage
- [ ] LLM judge (`judge` role, other provider): is each finding supported by its excerpts? (structured output)
- [ ] Run the checks in parallel, then a `verdict` node combines them
- [ ] Tests: inject one wrong number, a missing citation and an invented excerpt; each is caught by the right check

**Files:** `src/aegis/agents/verifier.py`, `tests/test_verifier.py`, notebook `06_verifier_and_retry`
**Done when:** each injected fault is caught by the right check, and a clean run passes.

### #33 · Step 2: Retry
**Goal:** fix only what failed, and never loop forever.
**Estimate:** ~1 h
- [ ] Add `retry_count` and `max_retries` (default 2)
- [ ] Router after `verdict`: pass → approval; fail with retries left → planner; fail with none left → reporter with `degraded`
- [ ] The planner reruns only `failed_step_ids`
- [ ] Pass the verifier's feedback into the rerun workers' prompts
- [ ] Test: a fault that's fixed on the second try → passes on retry 1
- [ ] Test: a permanent fault → stops after 2 retries with `degraded`

**Files:** `src/aegis/graphs/routing.py`, `tests/test_retry.py`
**Done when:** both tests pass, and the graph never runs more than 2 retries.

### #34 · Step 3: Human approval
**Goal:** a person approves, edits or rejects before the report is final.
**Estimate:** ~1.5 h
- [ ] `approval_policy(state)` as plain code: required in rank mode, when the top two are within 5%, when the sensitivity check flips, or when evidence is weak
- [ ] `ApprovalRequest`: ranking, findings, limitations, cost so far, reason approval is needed
- [ ] `ApprovalDecision`: approve, edit or reject; reviewer, comment, edits
- [ ] A dedicated `human_approval` node that calls `interrupt(payload)`, with nothing before the call (the node reruns on resume)
- [ ] Resume with `Command(resume=decision)`
- [ ] Edit (e.g. changed ranking basis) → back to analysis; reject → `finalize_rejected`
- [ ] Turn the Day 3 clarification end into an `interrupt` as well
- [ ] Test all three decisions with `InMemorySaver`

**Files:** `src/aegis/nodes/approval.py`, `src/aegis/nodes/clarify.py`, `tests/test_approval.py`, notebook `07_hitl_and_persistence`
**Done when:** approve, edit and reject each reach the right end state in the tests.

### #35 · Step 4: Persistence
**Goal:** a paused run survives a process restart.
**Estimate:** ~1.5 h
- [ ] `docker-compose.yml` with `postgres:16` and a named volume
- [ ] Add `DATABASE_URL` to settings and `.env.example`
- [ ] Install `langgraph-checkpoint-postgres`; create a `PostgresSaver` and call `setup()` once
- [ ] Use `thread_id = run_id`
- [ ] Check that your Pydantic models and `Decimal` values in state save and load correctly
- [ ] Kill-and-resume test: process 1 runs until the approval interrupt; process 2 resumes with the same `thread_id`
- [ ] Check checkpoint sizes; keep large data out of state

**Files:** `docker-compose.yml`, `src/aegis/persistence.py`, `scripts/kill_resume_demo.py`
**Done when:** a run paused for approval completes after the Python process is restarted.

### #36 · Step 5: Evals to 45 cases
**Goal:** cover verification and regressions.
**Estimate:** ~45 min
- [ ] Add 5 wrong-number cases, 5 missing-citation cases and 5 scope-mismatch cases
- [ ] Each case says which check should catch it
- [ ] Evaluator: verifier detection rate and false-alarm rate
- [ ] Save a baseline result file for regression comparison

**Files:** `evals/datasets/v1.jsonl`, `evals/evaluators.py`
**Done when:** the verifier catches every injected fault, and false alarms on clean cases are recorded.

---

## Day 6 — Nov 22 — Full graph and streaming API
**Status:** ⬜
**Deliverable:** the whole flow runs through the API.
**Gate:** a full run works using only curl.

### #37 · Step 1: Graph builder
**Goal:** one function builds all three experiment variants.
**Estimate:** ~1.5 h
- [ ] `build_graph(variant, checkpointer)`: A = baseline as one node; B = workers without verifier or approval; C = full
- [ ] Budget guard: on `BudgetExceededError`, go to the reporter with a partial result and `budget_exceeded`
- [ ] Each node adds a `node_events` entry (start, end, duration)
- [ ] Stream with `stream_mode=["updates", "custom"]` and print the events in the notebook
- [ ] Draw a diagram for each variant
- [ ] Test: each variant compiles and runs end to end with fake models

**Files:** `src/aegis/graphs/aegis.py`, `tests/test_graph_variants.py`, notebook `08_full_graph_streaming`
**Done when:** A, B and C all return a valid `FinalReport` on the same request.

### #38 · Step 2: Runs API
**Goal:** start runs over HTTP and watch their progress.
**Estimate:** ~2 h
- [ ] `runs` table: `run_id`, `user_id`, variant, status, request, created, updated, `cost_usd`, error
- [ ] `POST /runs`: validate the request, save the run, start the graph in the background, return 202 with the `run_id`
- [ ] `GET /runs/{id}`: status, cost, report if finished
- [ ] `GET /runs`: list runs, newest first
- [ ] `GET /runs/{id}/events`: Server-Sent Events stream of node events
- [ ] On startup, mark runs left `running` by a crash as resumable
- [ ] Errors return a safe message, never a stack trace

**Files:** `src/aegis/api/runs.py`, `src/aegis/db.py`, `tests/test_runs_api.py`
**Done when:** `curl` can start a run, stream its events and fetch the report.

### #39 · Step 3: Clarification and approval API
**Goal:** answer questions and give approvals over HTTP.
**Estimate:** ~1 h
- [ ] `POST /runs/{id}/clarification`: validate the answers and resume the run
- [ ] `POST /runs/{id}/approval`: validate the decision and resume the run
- [ ] Return 409 if the run isn't waiting for that input
- [ ] A second approval for the same run is rejected (idempotent)
- [ ] Tests for each endpoint, including the 409 cases

**Files:** `src/aegis/api/runs.py`, `tests/test_hitl_api.py`
**Done when:** a paused run can be clarified, approved and finished using only API calls.

### #40 · Step 4: API tests and demo script
**Goal:** the full API flow is proven offline and live.
**Estimate:** ~1 h
- [ ] End-to-end API test with fake models: start → clarify → approve → report
- [ ] `scripts/demo_flow.sh`: the same flow using curl
- [ ] One live end-to-end test with a budget cap

**Files:** `tests/test_api_e2e.py`, `scripts/demo_flow.sh`
**Done when:** the offline test passes in `pytest`, and the curl script finishes a live run.

---

## Day 7 — Nov 23 — Frontend, containers, CI, deployment (MVP)
**Status:** ⬜
**Deliverable:** the MVP is live over HTTPS.
**Gate:** you can submit a request, approve it and read the report in the deployed app.

### #41 · Step 1: Frontend (Next.js)
**Goal:** the two screens needed for the MVP.
**Estimate:** ~2.5 h
- [ ] Create the Next.js app (TypeScript) in `frontend/`
- [ ] Typed API client for the runs endpoints; `NEXT_PUBLIC_API_URL` in env
- [ ] Enable CORS on the backend for the frontend's origin
- [ ] Agent Workspace: request form (objective, subjects, factors, mode, time period, coverage)
- [ ] Clarification panel: show the questions and submit answers
- [ ] Live progress list using `EventSource`
- [ ] Report view: summary, comparison table, ranking, limitations, citations
- [ ] Approval Center: list of paused runs; detail view; approve, edit or reject

**Files:** `frontend/`
**Done when:** locally, you can run a request from the form through approval to the report.

### #42 · Step 2: Containers
**Goal:** the whole app runs from containers.
**Estimate:** ~1.5 h
- [ ] Backend `Dockerfile`: multi-stage, `uv sync --frozen`, non-root user, health check
- [ ] Frontend `Dockerfile`: Next.js standalone output
- [ ] `.dockerignore` for both, excluding `.env`, `.venv` and `node_modules`
- [ ] Extend `docker-compose.yml`: Postgres, backend and frontend
- [ ] Run the full flow with `docker compose up`
- [ ] Check that the images contain no secrets (`docker history`, look inside the image)

**Files:** `Dockerfile`, `frontend/Dockerfile`, `.dockerignore`, `docker-compose.yml`
**Done when:** `docker compose up` runs the full flow, and the images contain no secrets.

### #43 · Step 3: CI
**Goal:** every push is tested automatically.
**Estimate:** ~1 h
- [ ] `.github/workflows/ci.yml`: Python 3.12, `uv sync --frozen`, lint, offline `pytest`
- [ ] Frontend job: install, lint, build
- [ ] Docker build job for both images (no push)
- [ ] Cache uv and npm downloads
- [ ] Turn on branch protection on `main` so CI must pass

**Files:** `.github/workflows/ci.yml`
**Done when:** a pull request shows green checks, and a failing test blocks the merge.

### #44 · Step 4: Azure deployment
**Goal:** the app runs in Azure Container Apps.
**Estimate:** ~2.5 h
- [ ] Create a resource group and an Azure Container Registry
- [ ] Choose Postgres: Azure Flexible Server (burstable tier) or a free hosted Postgres. Compare their costs first.
- [ ] Create a Container Apps environment
- [ ] Backend app: secrets as Container Apps secrets, minimum 1 replica, HTTPS ingress
- [ ] Frontend app pointing at the backend URL
- [ ] Use a managed identity to pull images from the registry
- [ ] Set a budget alert in Azure Cost Management
- [ ] Deploy workflow: GitHub Actions with OIDC login; build, push and deploy images tagged with the Git SHA

**Files:** `.github/workflows/deploy.yml`, `docs/deployment.md`
**Done when:** a push to `main` deploys a new revision automatically.

### #45 · Step 5: Production smoke test
**Goal:** prove that the deployed MVP works.
**Estimate:** ~45 min
- [ ] `/health` and `/ready` return OK over HTTPS
- [ ] Run a full request through the UI to the report
- [ ] Restart the backend revision while a run waits for approval; approve it afterwards
- [ ] Check the container logs for secrets or prompts
- [ ] Add the live URL to the README

**Files:** `README.md`
**Done when:** every check passes on the deployed app.

---

## Day 8 — Nov 24 — Security and Execution Explorer
**Status:** ⬜
**Deliverable:** a hardened app and a view of each run's trace.
**Gate:** the security test suite passes.

### #46 · Step 1: Auth and roles
**Goal:** only signed-in users can use the app, and only reviewers can approve.
**Estimate:** ~2 h
- [ ] Choose the method: Container Apps built-in auth with Entra ID, or app-level JWT. Write down why.
- [ ] Roles: `requester` and `reviewer`
- [ ] FastAPI dependency that reads the user and role from each request
- [ ] Approval endpoints require `reviewer`
- [ ] Users only see their own runs; reviewers see runs waiting for approval
- [ ] Frontend: sign-in, and hide the Approval Center from non-reviewers
- [ ] Tests: 401 with no user; 403 when a requester approves; 404 for another user's run

**Files:** `src/aegis/api/auth.py`, `tests/test_auth.py`
**Done when:** all auth tests pass, and the deployed app requires sign-in.

### #47 · Step 2: Red-team cases
**Goal:** attacks are blocked and the tests prove it.
**Estimate:** ~2 h
- [ ] Prompt injection in the request objective
- [ ] Prompt injection hidden inside a saved web page
- [ ] A URL on a domain that isn't allowed
- [ ] Budget runs out mid-run → partial report with `budget_exceeded`
- [ ] A requester calls the approval endpoint
- [ ] Oversized input: 5,000 subjects, a 1 MB objective
- [ ] Code injection through the calculator
- [ ] Store the cases under `evals/security/`, each with the expected behaviour
- [ ] Run them offline in CI

**Files:** `evals/security/`, `tests/test_security.py`, notebook `10_security_redteam`
**Done when:** every case gives its expected behaviour, and the suite runs in CI.

### #48 · Step 3: Execution Explorer
**Goal:** see what happened inside any run.
**Estimate:** ~1.5 h
- [ ] Save `node_events` and tool calls to the database for each run
- [ ] `GET /runs/{id}/trace`: events in time order
- [ ] UI table: time, node, event, duration, tokens, cost, status
- [ ] Highlight retries and failed checks
- [ ] Show tool arguments, with secrets and long text cut out

**Files:** `src/aegis/api/trace.py`, `frontend/`
**Done when:** you can explain a retry by reading the trace for that run.

### #49 · Step 4: Evals to 60 cases
**Goal:** cover recovery, human approval and security.
**Estimate:** ~45 min
- [ ] 5 recovery cases: restart during workers, during approval, during reporting
- [ ] 5 approval cases: approve, edit, reject, double approval, approval by a requester
- [ ] 5 security cases taken from #47
- [ ] Run the full suite and save the results

**Files:** `evals/datasets/v1.jsonl`
**Done when:** 60 cases run, and every failure is either fixed or logged as an issue.

---

## Day 9 — Nov 25 — Full A/B/C evaluation
**Status:** ⬜
**Deliverable:** a report answering whether multi-agent orchestration with verification is worth its cost.
**Gate:** comparison report: success rate vs latency vs cost.

### #50 · Step 1: Grow to 100 cases
**Goal:** a frozen, balanced benchmark.
**Estimate:** ~1.5 h
- [ ] Add 40 cases, balanced across categories and both domains
- [ ] Remove near-duplicate cases
- [ ] Hand-check the expected answers of 10 random cases
- [ ] Freeze the dataset as `v2.jsonl`, and record a hash of the file

**Files:** `evals/datasets/v2.jsonl`
**Done when:** 100 valid cases are frozen, and the dataset test passes.

### #51 · Step 2: Run experiments A, B and C
**Goal:** a fair comparison of the three architectures on the same cases.
**Estimate:** ~1.5 h, plus run time
- [ ] Experiment runner: concurrency limit, a per-run budget, and a total budget for the whole experiment
- [ ] Use the same role → model mapping for all three variants
- [ ] Save each run's result, trajectory, tokens, cost and latency to JSONL
- [ ] Estimate the total cost before starting (cases × average cost per run)
- [ ] Run A, B and C

**Files:** `evals/experiment.py`, `evals/results/`
**Done when:** all 300 runs are saved, or the skipped ones are listed with the reason.

### #52 · Step 3: Metrics
**Goal:** numbers that answer the project's main question.
**Estimate:** ~1.5 h
- [ ] Correctness against the expected answers
- [ ] Clarification accuracy and routing accuracy
- [ ] Tool precision and recall
- [ ] Grounding rate: share of claims backed by valid evidence
- [ ] Latency: median and 95th percentile
- [ ] Cost per successful task
- [ ] Results table for each variant, plus charts

**Files:** `evals/metrics.py`, notebook `09_eval_lab`
**Done when:** one table compares A, B and C on every metric.

### #53 · Step 4: Failure analysis
**Goal:** understand why runs fail, not only how often.
**Estimate:** ~1.5 h
- [ ] Read 20 failed trajectories by hand
- [ ] Group them by cause: planning, tool use, grounding, verifier false alarm, budget, other
- [ ] Count each cause per variant
- [ ] Write `docs/eval-report.md`: the question, method, results, causes of failure, conclusion
- [ ] Open issues for the top 3 fixable causes

**Files:** `docs/eval-report.md`
**Done when:** the report answers "is multi-agent with verification worth the cost?" with evidence.

### #54 · Step 5: Evaluation Lab screen
**Goal:** browse experiments in the app.
**Estimate:** ~2 h
- [ ] API: list experiments, get metrics, list failed cases
- [ ] UI: experiment list and metrics table
- [ ] Compare two experiments side by side
- [ ] Drill down from a failed case to its run trace

**Files:** `src/aegis/api/evals.py`, `frontend/`
**Done when:** you can go from the metrics table to the trace of one failed case.

---

## Day 10 — Nov 26 — Docs and v1.0.0 release
**Status:** ⬜
**Deliverable:** a portfolio-ready v1.
**Gate:** definition of done met.

### #55 · Step 1: README
**Goal:** a first-time visitor understands and can run the project.
**Estimate:** ~1 h
- [ ] Update the description for the research-assistant design
- [ ] Architecture diagram and the headline eval numbers
- [ ] Screenshots of the Workspace, Approval Center and Evaluation Lab
- [ ] Quickstart: local run with Docker Compose
- [ ] Live demo URL and a note about the synthetic data

**Files:** `README.md`
**Done when:** someone else can run the project locally using only the README.

### #56 · Step 2: Architecture docs
**Goal:** explain how Aegis works and why it's built that way.
**Estimate:** ~1.5 h
- [ ] State table: keys, owners, reducers
- [ ] Graph diagram with the routing table
- [ ] Design decisions, each with its reason: tools do the maths, verifier on a different provider, interrupt in its own node, deterministic IDs
- [ ] Security model: auth, roles, web allow list, prompt-injection handling
- [ ] Cost controls: pricing, budget tracker, budget alerts

**Files:** `docs/architecture.md`
**Done when:** every major design choice is written down with its reason.

### #57 · Step 3: Demo scenarios
**Goal:** three repeatable demos.
**Estimate:** ~1 h
- [ ] Football compare, start to finish
- [ ] Platform rank with approval
- [ ] A request that needs clarification
- [ ] Save each input as a file and describe the expected result
- [ ] Record a short screen capture of each

**Files:** `docs/demos/`
**Done when:** all three demos run on the deployed app as described.

### #58 · Step 4: Rollback test
**Goal:** prove that a bad release can be undone quickly.
**Estimate:** ~45 min
- [ ] Deploy a deliberately broken revision (e.g. `/ready` fails)
- [ ] Switch traffic back to the previous revision
- [ ] Confirm the app works and paused runs still resume
- [ ] Write the steps in `docs/runbook.md`

**Files:** `docs/runbook.md`
**Done when:** the rollback took under 5 minutes, and the runbook is written.

### #59 · Step 5: Release v1.0.0
**Goal:** a tagged, documented v1.
**Estimate:** ~45 min
- [ ] `CHANGELOG.md` covering Days 1–10
- [ ] Tag `v1.0.0`
- [ ] GitHub release notes: features, eval summary, known limitations
- [ ] Close the Day 1–10 milestones

**Files:** `CHANGELOG.md`
**Done when:** the v1.0.0 release is published on GitHub.

---

## Day 11 — Nov 27 — RAG 1: document ingestion and vector store
**Status:** ⬜
**Deliverable:** your own documents (PDF, Markdown, HTML) are searchable, and every chunk traces back to a source.
**Gate:** ingesting a small corpus produces stable chunks with metadata.

- [ ] **Step 1: Choose the stack.**
  1. Vector store: `pgvector` in the Postgres you already run, so there's no new service
  2. Embeddings: an OpenAI or Foundry embedding model, chosen by role in the gateway
  3. Add embedding prices to `pricing.py`; ingestion counts toward the budget
- [ ] **Step 2: Corpus.**
  1. Pick 15–30 documents (vendor docs, reports, match reports)
  2. Store them under `data/corpus/`, with a `manifest.json` of title, origin, date and licence
- [ ] **Step 3: Loading and chunking.**
  1. Notebook `11_rag_ingestion`
  2. Loaders for PDF, Markdown and HTML
  3. Split by heading where possible, otherwise by size (about 500–800 tokens, with overlap)
  4. Give each chunk a stable ID (hash of document ID, position and text), so re-ingesting doesn't create duplicates
- [ ] **Step 4: Map to your schemas.**
  1. Each document becomes a `SourceRecord` with `kind="document"`. Extend the `kind` field, and its location rules, to allow this.
  2. Each chunk is stored with `source_id`, a page/section locator, `time_period` and `coverage`
- [ ] **Step 5: Ingestion CLI.** `aegis ingest data/corpus`: idempotent; it reports new, unchanged and removed chunks
- [ ] **Step 6: Tests.** Chunk IDs stay stable; re-ingesting is a no-op; metadata is complete

---

## Day 12 — Nov 28 — RAG 2: retrieval quality and retrieval evals
**Status:** ⬜
**Deliverable:** a retriever tool you can measure.
**Gate:** recall@5 meets the target you set on the labelled set.

- [ ] **Step 1: Basic retriever.** Vector search with top-k, plus metadata filters (subject, time period, coverage)
- [ ] **Step 2: Hybrid search.** Add keyword search (Postgres full-text) and merge both result lists (reciprocal rank fusion)
- [ ] **Step 3: Optional reranker.** Rerank the top 20 down to 5; keep it only if the evals improve
- [ ] **Step 4: Labelled retrieval set.**
  1. 30–50 questions, each with the chunk IDs that answer it
  2. Write them by hand from the corpus
- [ ] **Step 5: Retrieval evals** (notebook `12_rag_retrieval`). Recall@k, MRR, and latency for each setup: vector only, hybrid, hybrid + rerank
- [ ] **Step 6: Tool.** `retrieve_evidence(query, subject, factor, filters)` returns `EvidenceItem`s with `excerpt` and `locator`. Move to `src/aegis/rag/`.

---

## Day 13 — Nov 29 — RAG 3: RAG in the graph, grounding and evals
**Status:** ⬜
**Deliverable:** research workers use the documents, and the verifier checks claims against the retrieved text.
**Gate:** the faithfulness score on the RAG eval set beats the Day 9 baseline.

- [ ] **Step 1: Document research worker.** A new worker type that the planner can route to, alongside the dataset and web workers
- [ ] **Step 2: Planner update.** The planner chooses a source per step: dataset, documents or web
- [ ] **Step 3: Verifier update.**
  1. Faithfulness: each claim is supported by its cited excerpts
  2. Check that excerpts really exist in the stored chunk text, so quotes can't be invented
- [ ] **Step 4: Safety.**
  1. Treat document text as data and never as instructions
  2. Add test documents that contain hidden instructions
- [ ] **Step 5: RAG evals** (notebook `13_rag_evals`). Faithfulness, answer relevance, context precision, citation accuracy; compare with and without RAG
- [ ] **Step 6: UI.** Show cited excerpts with their document and page in the report

---

## Day 14 — Nov 30 — MCP 1: Aegis MCP server and MCP client
**Status:** ⬜
**Deliverable:** Aegis tools are available over MCP, and Aegis can use tools from approved external MCP servers.
**Gate:** an MCP client (e.g. Claude Desktop or the MCP Inspector) can call Aegis tools; the graph can call one external MCP tool.

- [ ] **Step 1: Learn the basics** (notebook `14_mcp`). Tools, resources and prompts; stdio vs streamable HTTP transports
- [ ] **Step 2: Aegis as an MCP server.**
  1. Use the official MCP Python SDK (`FastMCP`)
  2. Expose: `lookup_evidence`, `retrieve_evidence`, `calculator`, `weighted_score`
  3. Optionally expose finished reports as resources (`aegis://runs/{id}/report`)
  4. Reuse the existing plain functions; the MCP layer is a thin wrapper
  5. Test with the MCP Inspector over stdio
- [ ] **Step 3: Aegis as an MCP client.**
  1. Use `langchain-mcp-adapters` to load MCP tools as LangChain tools
  2. Configure servers in an allow list: name, transport, URL/command, permitted tools
  3. Connect one read-only external server (e.g. a filesystem or fetch server limited to a single folder or domain)
  4. Let the research worker use the allowed MCP tools
- [ ] **Step 4: Validation.** Convert every MCP tool result into your schemas (`SourceRecord`, `EvidenceItem`); reject anything that doesn't fit
- [ ] **Step 5: Tests.** Server tools return the same values as the direct functions; disallowed tools are never loaded

---

## Day 15 — Dec 1 — MCP 2: security, evals, deployment, v2.0.0
**Status:** ⬜
**Deliverable:** MCP is secure, measured and deployed, and v2 is released.
**Gate:** the MCP security suite passes; v2.0.0 is tagged.

- [ ] **Step 1: Security.**
  1. Treat tool descriptions from external servers as untrusted. Pin the expected descriptions and alert if they change.
  2. Treat tool outputs as data and never as instructions
  3. Set a timeout, a size limit and a rate limit for every MCP call
  4. Require human approval before any MCP tool that changes something
  5. Protect the HTTP MCP server with auth (bearer token or Entra ID)
- [ ] **Step 2: Red-team cases.** A malicious tool description, an injected tool output, a server that is too slow, an unapproved tool name
- [ ] **Step 3: Evals.** Compare native tools vs the same tools over MCP: correctness, latency, cost. Add MCP cases to the main suite.
- [ ] **Step 4: Deployment.** Deploy the Aegis MCP server as its own Container App on streamable HTTP; add it to CI
- [ ] **Step 5: Observability.** Log MCP calls in the Execution Explorer with server name, tool, latency and result size
- [ ] **Step 6: Release.** Update the README and architecture docs with the RAG and MCP sections; tag `v2.0.0`

---

## Notebook map

| Notebook | Day | Topic |
|---|---|---|
| `00_providers_and_gateway` | 1 | Providers, gateway, usage |
| `01_schemas_and_state` | 2 | Schemas, clarification, state and reducers |
| `02_tools` | 2 | Evidence lookup and calculators |
| `03_single_agent_baseline` | 3 | Experiment A |
| `04_planner_and_fanout` | 3 | Planner, `Send`, routing |
| `05_worker_subgraphs` | 4 | Research and analysis workers |
| `06_verifier_and_retry` | 5 | Verifier, bounded retry |
| `07_hitl_and_persistence` | 5 | Interrupts, Postgres checkpoints |
| `08_full_graph_streaming` | 6 | Full graph, streaming |
| `09_eval_lab` | 2 → 9 | Eval datasets and experiments |
| `10_security_redteam` | 8 | Security tests |
| `11_rag_ingestion` | 11 | Loading, chunking, embeddings |
| `12_rag_retrieval` | 12 | Retriever and retrieval evals |
| `13_rag_evals` | 13 | RAG in the graph, faithfulness |
| `14_mcp` | 14–15 | MCP server, client, security |

## If you fall behind

- **Cut first:** the Execution Explorer's visual polish (#48), the Evaluation Lab's side-by-side compare (#54), the reranker (Day 12), and MCP resources (Day 14)
- **Never cut:** persistence (#35), evals (#19, #26, #36, #49–#53), auth (#46), and the MCP security work (Day 15)
