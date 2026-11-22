"""End-to-end test set: runs the real /network-focus:brief skill headless on each case and checks the results.
  uv run python tests/evals/run_evals.py [--case NAME] [--grade]
Costs real Claude usage (~$1.20 per case, ~$0.20 per grade). Writes tests/evals/results/<date>.md. Exit 1 if any fail."""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "network-focus"
sys.path.insert(0, str(PLUGIN / "scripts"))
from nf_core.brief_checks import validate_brief  # noqa: E402
from nf_core.workspace import fingerprint  # noqa: E402

CASES = Path(__file__).resolve().parent / "cases"
RESULTS = Path(__file__).resolve().parent / "results"
HEADLESS = ["--output-format", "json", "--permission-mode", "dontAsk",
            "--allowedTools", "Read,Write,Edit,Bash(uv run *),Agent,Task"]
TIMEOUT = 900


def claude(prompt: str, extra: list[str], env: dict, log: Path | None = None) -> dict:
    """Run claude -p. With `log`, stream every event to that file and return the final result event."""
    if log:
        extra = [x if x != "json" else "stream-json" for x in extra] + ["--verbose"]
    try:
        p = subprocess.run(["claude", "-p", prompt, *extra], cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired as e:
        if log:
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or ""))
        return {"is_error": True, "result": f"timed out after {TIMEOUT}s"}
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(p.stdout)
        results = [e for e in (json.loads(l) for l in p.stdout.splitlines() if l.startswith("{"))
                   if e.get("type") == "result"]
        return results[-1] if results else {"is_error": True, "result": p.stderr[-2000:]}
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return {"is_error": True, "result": (p.stdout + p.stderr)[-2000:]}


def prepare(case: Path, tmp: Path) -> Path:
    home = tmp / "Network Focus"
    (home / "inbox").mkdir(parents=True)
    shutil.copy(PLUGIN / "templates" / "goals.md", home / "goals.md")
    roster = next(p for p in case.iterdir() if p.stem == "roster")
    dest = home / "inbox" / roster.name
    shutil.copy(roster, dest)
    setup = json.loads((case / "setup.json").read_text())
    if setup["mtime_days_ago"]:
        t = time.time() - setup["mtime_days_ago"] * 86400
        os.utime(dest, (t, t))
    if setup["history_same_sha_days_ago"]:
        run_date = (date.today() - timedelta(days=setup["history_same_sha_days_ago"])).isoformat()
        (home / ".history.json").write_text(json.dumps([{"sha256": fingerprint(dest), "file_name": dest.name,
                                                          "run_date": run_date, "brief": "earlier.pdf"}]))
    return home


def prepare_update(case: Path, tmp: Path) -> Path:
    """Monday's brief as this week's snapshot (built from the sample roster), the ticks so far, and the new roster."""
    from nf_core.checks import flags_for, run_checks
    from nf_core.goals import parse_goals
    from nf_core.roster import read_roster
    from nf_core.snapshot import build_snapshot
    from nf_core.workspace import week_of
    home = tmp / "Network Focus"
    (home / "inbox").mkdir(parents=True)
    (home / "briefs").mkdir()
    shutil.copy(PLUGIN / "templates" / "goals.md", home / "goals.md")
    shutil.copy(case / "roster.xlsx", home / "inbox" / "roster.xlsx")
    week = week_of(date.today()).isoformat()
    sample = ROOT / "sample-data" / "network_roster_terragrid.xlsx"
    contacts, _ = read_roster(sample)
    goals = parse_goals((home / "goals.md").read_text(encoding="utf-8"))
    roster = {"source": {"path": str(sample), "file_name": sample.name, "sha256": fingerprint(sample),
                         "as_of": date.today().isoformat(), "week_of": week},
              "goals": [g.to_dict() for g in goals],
              "contacts": [{**c.to_dict(), "text": c.text(), "flags": flags_for(c)} for c in contacts]}
    brief = json.loads((case / "base_brief.json").read_text())
    brief["week_of"] = week
    warnings = {"warnings": [i.to_dict() for i in run_checks(contacts, goals)]}
    (home / "briefs" / f"{week}-network-focus.json").write_text(json.dumps(build_snapshot(brief, roster, warnings)))
    marks = json.loads((case / "setup.json").read_text())["marks"]
    if marks:
        (home / ".progress.json").write_text(json.dumps({week: marks}))
    return home


def check_update(case: Path, home: Path, out: dict) -> list[str]:
    exp = json.loads((case / "expected.json").read_text())
    fails = [f"run errored: {str(out.get('result'))[:200]}"] if out.get("is_error") else []
    snap = json.loads(next((home / "briefs").glob("*-network-focus.json")).read_text())
    brief = snap["brief"]
    if not brief.get("updates"):
        return fails + [f"the brief wasn't updated. Reply: {str(out.get('result', ''))[:300]!r}"]
    focus = {f["name"]: f for f in brief["focus"]}
    considering = {c["name"] for c in brief.get("considering", [])}
    fails += [f"not placed: {n}" for n in exp["must_place"] if not focus.get(n, {}).get("new")]
    fails += [f"not in Worth considering: {n}" for n in exp["must_consider"] + exp["must_refuse"]
              if n not in considering or n in focus]
    fails += [f"dropped from focus: {n}" for n in exp["must_keep"] if n not in focus]
    problems = validate_brief(brief, json.loads((home / ".work" / "roster.json").read_text()))
    if problems:
        fails.append("validator: " + "; ".join(p.code for p in problems))
    if '"row_id"' in str(out.get("result", "")):
        fails.append("chat reply contains JSON")
    return fails


def check(case: Path, home: Path, out: dict) -> list[str]:
    exp = json.loads((case / "expected.json").read_text())
    work, briefs = home / ".work", home / "briefs"
    pdfs = list(briefs.glob("*.pdf")) if briefs.exists() else []
    fails = []
    if out.get("is_error"):
        fails.append(f"run errored: {str(out.get('result'))[:200]}")
    if exp["must_block"]:
        lr = subprocess.run([sys.executable, str(PLUGIN / "scripts" / "load_roster.py")], capture_output=True,
                            text=True, env={**os.environ, "NF_HOME": str(home)})
        code = json.loads(lr.stdout.strip().splitlines()[-1]).get("code")
        if code != exp["must_block"]:
            fails.append(f"expected block {exp['must_block']}, loader said {code}")
        if pdfs:
            fails.append("a PDF was produced for a blocked case")
        if "Notes" not in str(out.get("result", "")):
            fails.append("reply didn't pass on the missing column name")
        return fails
    if not pdfs:
        return fails + [f"no PDF produced. Reply: {str(out.get('result', ''))[:300]!r}"]
    brief, roster = json.loads((work / "brief.json").read_text()), json.loads((work / "roster.json").read_text())
    problems = validate_brief(brief, roster)
    if problems:
        fails.append("validator: " + "; ".join(p.code for p in problems))
    codes = {w["code"] for w in json.loads((work / "warnings.json").read_text())["warnings"]}
    picked = {x["name"] for x in brief["focus"] + brief["dormant"]}
    shown = picked | {x["name"] for x in brief["coming_up"]}
    fails += [f"missing pick: {n}" for n in exp["must_include"] if n not in picked]
    fails += [f"should not appear: {n}" for n in exp["must_exclude"] if n in shown]
    fails += [f"missing warning: {c}" for c in exp["must_warn"] if c not in codes]
    fails += [f"unexpected warning: {c}" for c in exp["must_not_warn"] if c in codes]
    if '"row_id"' in str(out.get("result", "")):
        fails.append("chat reply contains JSON")
    return fails


def grade(home: Path) -> dict | None:
    md = next((home / "briefs").glob("*.md"), None)
    if not md:
        return None
    w = home / ".work"
    out = claude(f"Grade this brief. Brief: {md} Roster: {w / 'roster.json'} Warnings: {w / 'warnings.json'} "
                 f"Rubric: {RESULTS.parent / 'rubric.md'}",
                 ["--agent", "eval-grader", "--output-format", "json", "--permission-mode", "dontAsk",
                  "--allowedTools", "Read"], dict(os.environ))
    m = re.search(r"\{.*\}", str(out.get("result", "")), re.S)
    try:
        g = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        g = None
    if g is not None:
        g["cost"] = out.get("total_cost_usd", 0)
    return g


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="")
    ap.add_argument("--grade", action="store_true")
    ap.add_argument("--page-tools", action="store_true",
                    help="allow only what the installed page allows (its background permission rules)")
    a = ap.parse_args()
    cases = [CASES / a.case] if a.case else sorted(p for p in CASES.iterdir() if p.is_dir())
    rows, failed = [], 0
    for case in cases:
        with tempfile.TemporaryDirectory() as tmp:
            is_update = json.loads((case / "setup.json").read_text()).get("kind") == "update"
            home = (prepare_update if is_update else prepare)(case, Path(tmp))
            t0 = time.time()
            extra = list(HEADLESS)
            if a.page_tools:
                sys.path.insert(0, str(PLUGIN / "app"))
                from install_app import background_allowed_tools
                extra[extra.index("--allowedTools") + 1] = background_allowed_tools(home, PLUGIN)
            out = claude("/network-focus:update" if is_update else "/network-focus:brief",
                         ["--plugin-dir", str(PLUGIN), *extra],
                         {**os.environ, "NF_HOME": str(home)}, log=RESULTS / "logs" / f"{case.name}.jsonl")
            secs = round(time.time() - t0)
            fails = (check_update if is_update else check)(case, home, out)
            g = grade(home) if (a.grade and not is_update
                                and not json.loads((case / "expected.json").read_text())["must_block"]) else None
            if g and (g.get("grounding", 0) < 4 or g.get("specificity", 0) < 4):
                fails.append(f"grader below 4 (grounding {g.get('grounding')}, specificity {g.get('specificity')})")
            failed += bool(fails)
            gtxt = (f"G{g['grounding']} S{g['specificity']} C{g['goal_coverage']} P{g['prioritization']} "
                    f"L{g['plain_language']}") if g else "-"
            rows.append((case.name, "FAIL" if fails else "PASS", "; ".join(fails) or "all checks met", secs,
                         out.get("total_cost_usd", 0) + (g or {}).get("cost", 0), gtxt, (g or {}).get("notes", "")))
            print(f"{case.name}: {'FAIL' if fails else 'PASS'} ({secs}s) {'; '.join(fails)}", flush=True)
    RESULTS.mkdir(exist_ok=True)
    lines = [f"# Test set results — {date.today().isoformat()}", "",
             "| Case | Result | Details | Time | Cost | Grade (G/S/C/P/L) |", "|---|---|---|---|---|---|"]
    lines += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]}s | ${r[4]:.2f} | {r[5]} |" for r in rows]
    notes = [f"- **{r[0]}:** {r[6]}" for r in rows if r[6]]
    if notes:
        lines += ["", "## Grader notes", ""] + notes
    out_file = RESULTS / f"{date.today().isoformat()}{'-' + a.case if a.case else ''}.md"
    out_file.write_text("\n".join(lines) + "\n")
    print(f"\n{len(rows) - failed}/{len(rows)} passed. Results: {out_file}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
