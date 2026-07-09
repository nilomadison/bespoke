# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common commands

```bash
# Activate venv first (every session)
source .venv/bin/activate

# Run app (mock LLM avoids needing OPENROUTER_API_KEY)
BESPOKE_MOCK_LLM=1 uvicorn src.web.app:app --reload

# Tests — single file or single test
pytest tests/test_planner.py
pytest tests/test_planner.py::test_build_plan_returns_plan_items

# Lint
ruff check .
ruff format .

# Migrations (SQLite via Alembic). `0001_baseline` is a full-schema migration,
# so `alembic upgrade head` builds a blank db from scratch AND applies new
# migrations to an existing one. (The old 0001-0007 history was squashed into it.)
alembic upgrade head
alembic revision --autogenerate -m "msg"

# Re-seed local DB from data/seed.yaml (safe to re-run; upserts, no duplicates)
python -m src.db.seed

# Wipe and reseed from scratch. `python -m src.db.seed` builds the schema via
# create_all() in init_db(), which is kept in lockstep with 0001_baseline, so the
# stamp just marks the db as current. (`alembic upgrade head` before seeding works too.)
rm data/bespoke.db && python -m src.db.seed && alembic stamp head

# Compare two tailoring sessions (prompt A/B)
python -m src.tools.prompt_compare {list|analyze|plan|generate|cover_letter} <id_a> <id_b>
```

## Architecture

The user's career database is the only source of truth; resumes and cover letters are generated artifacts. A `TailoringSession` walks through three LLM stages, each storing its output as JSON on the session row alongside a `sha256[:12]` hash of the prompt file used to produce it.

**Pipeline (orchestrated in `src/web/routes/tailor.py`):**

1. **Analyze** (`src/tailor/analyzer.py`) — extracts structured signals (required/preferred skills, role_level, tone, etc.) from the pasted JD into `analysis_json`.
2. **Plan** (`src/tailor/planner.py`) — `serialize_career()` dumps the entire DB to JSON; the LLM picks items to include; the result is materialized as `PlanItem` rows.
3. **Human review** — on the plan-review page the user can toggle `PlanItem.include`, edit `emphasis_note`, drag-reorder (`PlanItem.sort_order`, via SortableJS + `POST /tailor/{id}/plan/reorder`), and add items the LLM missed via the picker (`GET/POST /tailor/{id}/plan/add`, which writes new `PlanItem` rows using the polymorphic soft-FK). If analysis itself failed, `POST /tailor/{id}/retry-analysis` clears the prior plan and re-runs without losing the JD. **This step is load-bearing, not just UX.** It is the chokepoint that lets the user catch upstream hallucinations and override scoring before any prose is written. Generation is gated on this step; do not add an "auto-advance" path that skips it.
4. **Generate** (`src/tailor/generator.py`) — `resolve_plan_items()` (`src/tailor/resolver.py`) hydrates the soft-FK `PlanItem` rows into display-ready dicts grouped by job, then the LLM writes prose into `generated_json`.
5. **Cover letter** (`src/tailor/cover_letter.py`) — optional, reuses the resolved plan items so the cover letter cites the same achievements as the resume. This is the **most prose-fragile artifact** — it has a higher LLM-tells bar than resume bullets and is the most likely place for stilted phrasing or invented narrative to leak in. Treat changes to its prompt with extra scrutiny.

`src/tailor/scorer.py` is **deterministic, not LLM** — it computes skill coverage and role-level fit for the plan-review page. Keep it that way.

**Prompts** live under `prompts/{analyze,plan,generate,cover_letter}/` as `system.md` + `user.md` pairs. `src/llm/prompt_loader.py` loads them by dotted name (`load_prompt("plan.system")`), caches with `lru_cache`, and exposes `get_prompt_hash()`. Every session records exactly which prompt version produced its output, which is what makes `prompt_compare` meaningful.

**LLM client** is selected at runtime: real `OpenRouterClient` (`src/llm/openrouter.py`) or `MockLLMClient` (`src/llm/mock.py`) when `BESPOKE_MOCK_LLM=1`. Sync DB + async LLM is bridged by running httpx calls in a `ThreadPoolExecutor` from sync route handlers.

**Models (`src/models/`):** `Profile` is a singleton (`id=1`, contact info + baseline summary). `Job` owns `Achievement`, `Project`, and `JobSkill` rows. `TailoringSession` has many `PlanItem` (cascade delete). `PlanItem.reference_id` is a **polymorphic soft-FK** (no DB constraint) — `item_type` (enum: JOB, ACHIEVEMENT, SKILL_GROUP, PROJECT, EDUCATION, CERTIFICATION) tells the resolver which table to look up. This is intentional; see invariants below.

**HTMX pattern:** short-row entities (Skills, Education, Certs, Achievements) use inline edit returning fragment templates from `src/web/templates/`. Jobs and Projects (many fields) get their own edit pages. Status-polling endpoints like `/tailor/{id}/status` return spinner partials with `HX-Redirect` headers when background analysis/generation finishes.

**Render:** two parallel single-pass renderers read `generated_json` + profile dict and stream bytes — both ATS-friendly (no tables, no text boxes, single-column flow, 0.75" margins).

- `src/render/docx_renderer.py` (`POST /tailor/{id}/export`) — python-docx, Calibri 11pt.
- `src/render/pdf_renderer.py` (`GET /tailor/{id}/export.pdf`) — ReportLab, Helvetica 11pt (PDF-safe substitute for Calibri; bundling Calibri.ttf is a license issue).

**`generated_json` is mutable post-generation.** The result page exposes inline-edit routes (`POST /tailor/{id}/result/field`, `/result/bullet/add`, `/result/bullet/delete`) that mutate `session.generated_json` directly with no LLM call. Both exporters read from the live JSON, so user edits flow through to .docx and .pdf. Field paths are validated against the allowlist regex set in `tailor.py` (`_ALLOWED_RESULT_PATHS`) — extend that list when adding new editable fields, and do not loosen it to accept arbitrary paths.

## The no-fabrication invariant

**No content in any generated artifact may assert facts about the candidate that aren't traceable to the career database.** This applies to every LLM-written surface — resume bullets, the tailored summary, the cover letter, and any future generated prose. Metrics, dates, titles, employers, technologies, and narrative claims must all resolve back to a row in the career DB.

Tests that enforce pieces of this contract:

- `tests/test_generator.py::test_anti_hallucination_metric_in_context` — the metric a bullet cites must appear in the input context the generator sees.
- `tests/test_resolver.py` — the resolver only surfaces data attached to `PlanItem` rows, so the generator literally cannot see anything else. Tests like `test_skill_group_item_uses_emphasis_note` and `test_missing_reference_id_returns_none_text` pin this contract.
- `tests/test_planner.py::test_build_plan_skips_unknown_types` — the planner cannot conjure plan items pointing at types the resolver doesn't know how to hydrate.

Any change to the generator, resolver, planner, or their prompts must keep these green. If you add a new generated artifact (e.g. LinkedIn blurb), it must go through `resolve_plan_items()` or an equivalent that gates the LLM's input to DB-backed data, and it needs an analogous traceability test.

## Invariants — do not change without explicit discussion

- **Polymorphic soft-FK on `PlanItem.reference_id`** — do not "fix" this with real foreign keys or one-table-per-type. The resolver and `prompt_compare` rely on the current shape.
- **Scorer stays deterministic** — no LLM calls in `src/tailor/scorer.py`. It is the cheap, reproducible signal users see while reviewing the plan.
- **Prompt hashing is mandatory** — every LLM call path must record the prompt hash on the session. Do not bypass `get_prompt_hash()` or stop persisting `*_prompt_version` fields; that is what makes the compare CLI and reproducibility work.
- **Plan-review step is gated** — do not add a code path that goes from analyze → generate without the user's plan edits.
- **Sync SQLAlchemy 2 only** — don't introduce `AsyncSession`. LLM calls are the only async surface.

## Discipline for prompt and schema changes

- **Prompt edits.** When you change anything under `prompts/`, run two sessions over the same fixture JD (one before, one after) and use `python -m src.tools.prompt_compare {analyze|plan|generate|cover_letter} <id_before> <id_after>` to inspect the delta. Commit the prompt change only after reading that diff.
- **Model edits.** Any change to `src/models/` requires a generated and committed Alembic migration in `alembic/versions/`, stacked on top of `0001_baseline` (the consolidated full-schema baseline). `create_all()` in `init_db()` and the baseline are kept in lockstep — they must produce identical schema — so autogenerate the migration (`alembic revision --autogenerate -m "msg"`) and commit it alongside the model change. Don't ship a model change with "I'll do the migration later," or the next person to run `alembic upgrade head` will diverge from `create_all()`.

## Conventions

- **Tests use `tests/conftest.py` fixtures**: `db_session` (in-memory SQLite, seeds `Profile(id=1)`) and `client` (FastAPI TestClient with overridden `get_session`). Web route tests use `client`; domain logic tests use `db_session`.
- **Config** lives in `src/config.py` as a `Settings` dataclass populated from `os.getenv`. Don't add pydantic-settings. New env vars go there.
- **Python 3.14 deprecation warnings** from FastAPI/Starlette (`asyncio.iscoroutinefunction`) are upstream; ignore them.
