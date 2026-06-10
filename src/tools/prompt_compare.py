"""Prompt comparison CLI — compare two sessions' LLM outputs by stage.

Usage:
    python -m src.tools.prompt_compare list
    python -m src.tools.prompt_compare analyze <session_id_1> <session_id_2>
    python -m src.tools.prompt_compare plan    <session_id_1> <session_id_2>
    python -m src.tools.prompt_compare generate <session_id_1> <session_id_2>

The DB already stores analysis_json, plan_items, and generated_json alongside the
prompt version hash (sha256[:12]) that produced them. Use this tool to compare two
sessions run with different prompt versions against the same job description.

Each mode shows what's *meaningfully* different for that stage rather than a raw
text diff:
  analyze  — field-by-field comparison of the structured analysis JSON
  plan     — which items were selected/dropped relative to each other
  generate — summary text and bullet-by-bullet experience comparison
"""

import argparse
import difflib
import sys

from sqlalchemy import select

from src.db.engine import SessionLocal
from src.models.tailoring import PlanItem, TailoringSession

# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

_USE_COLOR = sys.stdout.isatty()


def _c(text: str, code: str) -> str:
    if not _USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def green(t: str) -> str:
    return _c(t, "32")


def red(t: str) -> str:
    return _c(t, "31")


def yellow(t: str) -> str:
    return _c(t, "33")


def bold(t: str) -> str:
    return _c(t, "1")


def dim(t: str) -> str:
    return _c(t, "2")


def _header(title: str) -> None:
    print()
    print(bold(f"── {title} " + "─" * max(0, 60 - len(title))))


def _row(label: str, a: str, b: str, width: int = 26) -> None:
    changed = a != b
    label_str = f"  {label:<{width}}"
    if not changed:
        print(f"{label_str} {dim(a)}")
    else:
        print(f"{label_str} {red(a or '(none)')}")
        print(f"  {'':>{width+1}} {green(b or '(none)')}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_session(db, session_id: int) -> TailoringSession:
    session = db.get(TailoringSession, session_id)
    if session is None:
        print(f"Session {session_id} not found.", file=sys.stderr)
        sys.exit(1)
    return session


def _load_plan_items(db, session_id: int) -> list[PlanItem]:
    return list(
        db.scalars(
            select(PlanItem).where(PlanItem.session_id == session_id).order_by(PlanItem.sort_order)
        ).all()
    )


def _item_key(item: PlanItem) -> str:
    return f"{item.item_type.value}:{item.reference_id}"


def _list_join(lst: list) -> str:
    return ", ".join(lst) if lst else "(none)"


# ---------------------------------------------------------------------------
# list mode
# ---------------------------------------------------------------------------


def cmd_list(db) -> None:
    sessions = db.scalars(
        select(TailoringSession).order_by(TailoringSession.created_at.desc())
    ).all()
    if not sessions:
        print("No sessions found.")
        return
    print(
        bold(
            f"\n{'ID':>4}  {'Job title':<30}  {'Company':<20}  {'Status':<14}  "
            f"{'Analyze v':<12}  {'Generate v':<12}"
        )
    )
    print("─" * 100)
    for s in sessions:
        print(
            f"{s.id:>4}  {s.job_title[:29]:<30}  {s.company_name[:19]:<20}  "
            f"{s.status.value:<14}  {(s.analysis_prompt_version or ''):<12}  "
            f"{(s.generation_prompt_version or ''):<12}"
        )


# ---------------------------------------------------------------------------
# analyze mode
# ---------------------------------------------------------------------------


def cmd_analyze(db, id1: int, id2: int) -> None:
    s1, s2 = _load_session(db, id1), _load_session(db, id2)

    _header(f"ANALYZE  session {id1} → session {id2}")
    print(
        f"  {'Prompt version':<26} {dim(s1.analysis_prompt_version or '?')}"
        f"  →  {s2.analysis_prompt_version or '?'}"
    )
    print(f"  {'Job title':<26} {s1.job_title}")

    a1 = s1.analysis_json or {}
    a2 = s2.analysis_json or {}

    if not a1 and not a2:
        print("  Neither session has analysis output.")
        return

    _header("Scalar fields")
    for field in ("role_level", "domain", "tone"):
        _row(field, str(a1.get(field, "")), str(a2.get(field, "")))

    _header("required_skills")
    r1 = set(a1.get("required_skills", []))
    r2 = set(a2.get("required_skills", []))
    for skill in sorted(r1 | r2):
        in1, in2 = skill in r1, skill in r2
        marker = "  " if (in1 and in2) else (green("+ ") if in2 and not in1 else red("- "))
        print(f"  {marker}{skill}")

    _header("preferred_skills")
    p1 = set(a1.get("preferred_skills", []))
    p2 = set(a2.get("preferred_skills", []))
    for skill in sorted(p1 | p2):
        in1, in2 = skill in p1, skill in p2
        marker = "  " if (in1 and in2) else (green("+ ") if in2 and not in1 else red("- "))
        print(f"  {marker}{skill}")

    _header("impact_signals")
    sig1 = set(a1.get("impact_signals", []))
    sig2 = set(a2.get("impact_signals", []))
    for sig in sorted(sig1 | sig2):
        in1, in2 = sig in sig1, sig in sig2
        marker = "  " if (in1 and in2) else (green("+ ") if in2 and not in1 else red("- "))
        print(f"  {marker}{sig}")

    _header("emphasis_guidance")
    eg1 = a1.get("emphasis_guidance", "")
    eg2 = a2.get("emphasis_guidance", "")
    if eg1 == eg2:
        print(f"  {dim(eg1 or '(none)')}")
    else:
        print(f"  {red(eg1 or '(none)')}")
        print(f"  {green(eg2 or '(none)')}")

    print()


# ---------------------------------------------------------------------------
# plan mode
# ---------------------------------------------------------------------------


def cmd_plan(db, id1: int, id2: int) -> None:
    s1, s2 = _load_session(db, id1), _load_session(db, id2)
    items1 = _load_plan_items(db, id1)
    items2 = _load_plan_items(db, id2)

    _header(f"PLAN  session {id1} → session {id2}")
    print(f"  Session {id1}: {len(items1)} items  (prompt {s1.analysis_prompt_version or '?'})")
    print(f"  Session {id2}: {len(items2)} items  (prompt {s2.analysis_prompt_version or '?'})")

    keys1 = {_item_key(i): i for i in items1}
    keys2 = {_item_key(i): i for i in items2}
    all_keys = list(dict.fromkeys(list(keys1) + list(keys2)))  # preserve order

    only_in_1 = [k for k in all_keys if k in keys1 and k not in keys2]
    only_in_2 = [k for k in all_keys if k not in keys1 and k in keys2]
    in_both = [k for k in all_keys if k in keys1 and k in keys2]

    _header(f"In both ({len(in_both)})")
    for k in in_both:
        i1, i2 = keys1[k], keys2[k]
        status1 = "✓" if i1.include else "○"
        status2 = "✓" if i2.include else "○"
        include_diff = f" [{status1}→{status2}]" if i1.include != i2.include else ""
        print(f"  {dim(k)}{include_diff}")
        if i1.llm_rationale != i2.llm_rationale:
            print(f"    rationale: {red(i1.llm_rationale or '?')}")
            print(f"               {green(i2.llm_rationale or '?')}")

    if only_in_1:
        _header(f"Only in session {id1} ({len(only_in_1)})")
        for k in only_in_1:
            item = keys1[k]
            print(f"  {red('- ')}{k}  {dim(item.llm_rationale or '')}")

    if only_in_2:
        _header(f"Only in session {id2} ({len(only_in_2)})")
        for k in only_in_2:
            item = keys2[k]
            print(f"  {green('+ ')}{k}  {dim(item.llm_rationale or '')}")

    print()


# ---------------------------------------------------------------------------
# generate mode
# ---------------------------------------------------------------------------


def _diff_text(label: str, t1: str, t2: str) -> None:
    if t1 == t2:
        print(f"  {label}: {dim(t1[:80] + ('…' if len(t1) > 80 else ''))}")
        return
    print(f"  {label}:")
    differ = difflib.unified_diff(
        t1.splitlines(), t2.splitlines(), fromfile="session A", tofile="session B", lineterm=""
    )
    for line in list(differ)[2:]:  # skip the --- +++ header
        if line.startswith("+"):
            print(f"    {green(line)}")
        elif line.startswith("-"):
            print(f"    {red(line)}")
        else:
            print(f"    {dim(line)}")


def cmd_generate(db, id1: int, id2: int) -> None:
    s1, s2 = _load_session(db, id1), _load_session(db, id2)

    _header(f"GENERATE  session {id1} → session {id2}")
    print(f"  Session {id1}: prompt {s1.generation_prompt_version or '(none)'}")
    print(f"  Session {id2}: prompt {s2.generation_prompt_version or '(none)'}")

    g1 = s1.generated_json or {}
    g2 = s2.generated_json or {}

    if not g1 and not g2:
        print("  Neither session has generated output.")
        return

    _header("Summary")
    _diff_text("summary", g1.get("summary", ""), g2.get("summary", ""))

    _header("Skills")
    _diff_text("skills", g1.get("skills", ""), g2.get("skills", ""))

    _header("Experience")
    exps1 = {e.get("company", "") + "/" + e.get("title", ""): e for e in g1.get("experience", [])}
    exps2 = {e.get("company", "") + "/" + e.get("title", ""): e for e in g2.get("experience", [])}
    all_exp_keys = list(dict.fromkeys(list(exps1) + list(exps2)))

    for key in all_exp_keys:
        print(f"\n  {bold(key)}")
        e1 = exps1.get(key, {})
        e2 = exps2.get(key, {})
        if not e1:
            print(f"    {green('(new in session ' + str(id2) + ')')}")
            for b in e2.get("bullets", []):
                print(f"    {green('+ ' + b)}")
            continue
        if not e2:
            print(f"    {red('(dropped in session ' + str(id2) + ')')}")
            continue
        bullets1 = e1.get("bullets", [])
        bullets2 = e2.get("bullets", [])
        for b in bullets1:
            if b in bullets2:
                print(f"    {dim('  ' + b[:90])}")
            else:
                print(f"    {red('- ' + b)}")
        for b in bullets2:
            if b not in bullets1:
                print(f"    {green('+ ' + b)}")

    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m src.tools.prompt_compare",
        description="Compare LLM outputs across two sessions by stage.",
    )
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color")
    sub = parser.add_subparsers(dest="mode", required=True)

    sub.add_parser("list", help="List all sessions")

    for mode in ("analyze", "plan", "generate"):
        sp = sub.add_parser(mode, help=f"Compare {mode} stage")
        sp.add_argument("session_a", type=int)
        sp.add_argument("session_b", type=int)

    args = parser.parse_args()

    global _USE_COLOR
    if args.no_color:
        _USE_COLOR = False

    db = SessionLocal()
    try:
        if args.mode == "list":
            cmd_list(db)
        elif args.mode == "analyze":
            cmd_analyze(db, args.session_a, args.session_b)
        elif args.mode == "plan":
            cmd_plan(db, args.session_a, args.session_b)
        elif args.mode == "generate":
            cmd_generate(db, args.session_a, args.session_b)
    finally:
        db.close()


if __name__ == "__main__":
    main()
