# Prompts

Each prompt is a versioned file. The code reads them at runtime via `src/llm/prompt_loader.py` and stores a sha256 hash of the file contents in the database alongside the output it produced. This makes it possible to tell which prompt version generated any given analysis or resume.

---

## Prompt lifecycle

1. **Edit** the `.md` file.
2. **Restart the dev server** — `prompt_loader` is `lru_cache`'d, so a restart is required.
3. **Test** by running the full flow with `BESPOKE_MOCK_LLM=0` and a real job description.
4. **Commit** the file. The git commit hash is not used for versioning; the sha256 of the file content is (so uncommitted local edits are captured too).

---

## analyze/

**Stage 1: job description analysis.**

| File | Purpose |
|---|---|
| `system.md` | Sets the analyst role; specifies the exact JSON output schema. |
| `user.md` | Template with `{job_description}` placeholder. |

**Output schema** (parsed into `JobAnalysis` dataclass in `src/tailor/analyzer.py`):

```json
{
  "required_skills": ["..."],
  "preferred_skills": ["..."],
  "role_level": "senior",
  "domain": "backend",
  "tone": "startup-casual",
  "impact_signals": ["scale", "reliability"],
  "red_flags": [],
  "emphasis_guidance": "1-2 sentence note to the strategist."
}
```

**What counts as a regression:**
- Any field missing from the output causes a `KeyError` in `analyzer.py` (fail loudly).
- `role_level` outside the allowed vocabulary means the plan template renders a raw string.
- `impact_signals` outside the vocabulary means planner selection logic silently misses overlaps.
- Non-JSON output (markdown prose, code fences) — the code strips fences but multi-level nesting will crash `json.loads`.

**Fixture:** `tests/fixtures/sample_analysis.json`

---

## plan/

**Stage 1b: item selection planning.**

| File | Purpose |
|---|---|
| `system.md` | Sets the strategist role; lists hard constraints and selection guidelines. |
| `user.md` | Template with `{analysis_json}` and `{career_context}` placeholders. |

**Output schema** (parsed into `PlanItem` rows in `src/tailor/planner.py`):

```json
{
  "items": [
    {
      "type": "achievement",
      "id": 42,
      "emphasis_note": "Lead with the reliability angle.",
      "rationale": "Directly maps to the impact_signals in the analysis."
    }
  ]
}
```

Allowed `type` values: `job`, `achievement`, `skill_group`, `project`, `education`, `certification`.
For `skill_group`, `id` must be `null`.

**Hard constraints (enforced by the prompt, not the code):**
- Every `id` must exist in the career data provided as input. The code does not validate this — it uses soft FKs. A hallucinated ID will silently produce a plan item that points to nothing.
- `skill_group` is the only type that allows `id: null`. Any other type with `null` is a bug.

**What counts as a regression:**
- Items with `type` values not in the allowed enum — `planner.py` silently skips them, producing a shorter plan than expected.
- Hallucinated `id` values — the plan renders but the resume generator will fail to resolve them.
- Missing `items` key — `plan_data.get("items", [])` returns empty list; the session gets zero plan items.
- Repeated IDs for the same type — technically allowed, will produce duplicate rows.

**Fixture:** `tests/fixtures/sample_plan.json`

---

## generate/

**Stage 2: resume prose generation.**

| File | Purpose |
|---|---|
| `system.md` | Sets the resume writer role; HARD CONSTRAINT: only use data from input; specifies JSON output schema. |
| `user.md` | Template with `{job_title}`, `{company_name}`, `{analysis_json}`, `{plan_context}` placeholders. |

**Key constraint:** The generator must only use achievement text, metrics, and descriptions that appear verbatim in the resolved plan items. It must never invent numbers, outcomes, or responsibilities.

**Output schema** (parsed from `TailoringSession.generated_json` and rendered in `tailor/result.html`):

```json
{
  "summary": "...",
  "experience": [
    {
      "company": "...",
      "title": "...",
      "dates": "...",
      "bullets": ["..."]
    }
  ],
  "skills": "...",
  "projects": [{"name": "...", "description": "..."}],
  "education": [{"institution": "...", "degree": "...", "dates": "..."}]
}
```

**What counts as a regression:**
- Missing top-level fields — `result.html` silently skips empty sections, producing a blank resume.
- Bullets with metrics not in the input career data — the anti-hallucination test in `tests/test_generator.py` catches this at the context-building level.
- Non-JSON output (markdown prose, code fences) — the code strips fences but multi-level nesting will crash `json.loads`.
- Empty `experience` list — a valid parse but a useless resume.

**Fixture:** `tests/fixtures/sample_generation.json`

---

## cover_letter/

**Stage 3 (optional): cover letter generation.** Reuses the same resolved plan items as `generate/` so the letter cites the same achievements as the resume.

| File | Purpose |
|---|---|
| `system.md` | Sets the writer role; HARD CONSTRAINT: only use data from input; bans LLM-tell phrases and rhetorical moves; caps length and structure; specifies JSON output schema. |
| `user.md` | Template with `{job_title}`, `{company_name}`, `{analysis_json}`, `{plan_context}` placeholders. |

**Output schema** (parsed from `TailoringSession.cover_letter_json` and rendered in the cover letter view):

```json
{
  "salutation": "Dear Hiring Team,",
  "paragraphs": ["...", "..."],
  "closing": "..."
}
```

**This prompt is unusual.** Unlike `analyze/` and `plan/`, which do structural extraction, the cover letter prompt is doing substantial voice and style work. It contains a banned-phrases list organized by rhetorical move (openings, bridge sentences, self-characterization, closings, style tics), structural caps (2–3 paragraphs, 130–200 words, no four-paragraph shape), and a positive-example fragment in the target voice. Read the maintainer comment at the top of `system.md` for the iteration history and the specific failure modes each constraint addresses before editing.

**Hard constraints (enforced by the prompt, not the code):**
- No fabrication: every concrete claim — metrics, project names, technologies, motivations, level of seniority — must trace to the resolved plan items.
- The letter must reference at least one item from the career data by its actual name and one concrete detail.
- Do not soften gaps with "I'm comfortable in [X]" / "I've worked with [X]" when the data does not list X.

**What counts as a regression:**
- Output wrapped in markdown fences — `_strip_fences()` in `src/tailor/cover_letter.py` handles single-level fences, but nested fences or trailing prose will crash `json.loads`.
- A "why this company" paragraph asserting the candidate's enthusiasm or alignment with company values that aren't in the input — silent fabrication; not caught by tests.
- Recurrence of the canonical four-paragraph (opening / evidence / fit / close) shape — not a hard break, but the structural shape itself is a tell that defeats the prompt's purpose.
- Word counts persistently outside the 130–200 range across multiple samples — indicates the model is ignoring the length cap and the prompt needs strengthening.
- Hedge phrases for tech the candidate's data does not list — fabrication; not caught by tests.

The voice quality of the output is fundamentally a human-judgment evaluation. Use a real JD and the candidate's real seed data; read the output the way a recruiter would. The fixture `sample_cover_letter.json` is illustrative only — it is not a quality benchmark.

**Fixture:** `tests/fixtures/sample_cover_letter.json`
