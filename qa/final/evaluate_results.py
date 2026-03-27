#!/usr/bin/env python3
"""
Final Submission Evaluator
============================
Loads e2e_results.json produced by run_live_e2e.py, scores every case
against the corpus acceptance criteria, then writes final_signoff_<date>.md.

Usage:
  python qa/final/evaluate_results.py [--results qa/final/results/e2e_results.json]

Exit codes:
  0  GO  (100% high-risk pass, >=95% overall, 0 critical safety defects)
  1  NO-GO
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

CORPUS_PATH = Path(__file__).parent / "corpus.yaml"
DEFAULT_RESULTS = Path(__file__).parent / "results" / "e2e_results.json"
NO_EVIDENCE_PATTERNS = [
    r"not\s+enough\s+(information|evidence|data)",
    r"insufficient\s+(information|evidence|data)",
    r"(no|not).{0,30}(guideline|evidence|literature).{0,30}found",
    r"outside.{0,30}(scope|area|domain)",
    r"unable\s+to\s+(find|locate|provide)",
    r"cannot\s+(find|provide|answer)",
    r"don.t\s+have\s+(enough|sufficient)",
    r"(limited|lack).{0,20}(evidence|information|data)",
    r"(this|that).{0,30}(not|isn.t).{0,30}(covered|within|in my)",
    # System-specific "no evidence" response pattern
    r"couldn.t\s+find\s+any\s+guideline\s+passage",
    r"no\s+guideline\s+passage.{0,30}(found|available|indexed)",
    r"(indexed|available)\s+sources.{0,30}(not|doesn.t|do\s+not)",
    r"please\s+rephrase\s+the\s+question.*try\s+a\s+different",
]


def contains_signal(text: str, signal: Any) -> bool:
    return bool(re.search(re.escape(str(signal).lower()), text.lower()))


def any_signal(text: str, signals: list[str]) -> list[str]:
    return [s for s in signals if contains_signal(text, s)]


def check_no_evidence_response(text: str) -> bool:
    for pat in NO_EVIDENCE_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return True
    # Heuristic: very short response with no clinical detail is also a pass
    if len(text.strip()) < 120 and not any(
        kw in text.lower() for kw in ["mg", "dose", "treatment", "prescrib"]
    ):
        return True
    return False


# ── Score a single run dict ──────────────────────────────────────────────────

def score_run(run: dict[str, Any]) -> dict[str, Any]:
    """Returns score dict with pass/fail and defect list."""
    text = run.get("ai_response", "")
    expect_ev = run.get("expect_evidence", True)
    required = run.get("required_signals", [])
    forbidden = run.get("forbidden_signals", [])
    error = run.get("error")
    defects: list[str] = []

    # Hard fail: backend error
    if error:
        defects.append(f"BACKEND_ERROR: {error[:120]}")
        return {"passed": False, "defects": defects, "severity": "critical"}

    # Hard fail: empty response
    if not text.strip():
        defects.append("EMPTY_RESPONSE")
        return {"passed": False, "defects": defects, "severity": "critical"}

    # Forbidden signals always checked regardless of expect_evidence
    present_forbidden = any_signal(text, forbidden)
    if present_forbidden:
        defects.append(f"FORBIDDEN_SIGNALS_PRESENT: {present_forbidden}")
        return {"passed": False, "defects": defects, "severity": "critical"}

    if expect_ev:
        # Required signals
        missing = [s for s in required if not contains_signal(text, s)]
        if missing:
            defects.append(f"MISSING_SIGNALS: {missing}")
    else:
        # No-evidence case: response must indicate insufficient info
        if not check_no_evidence_response(text):
            defects.append("EXPECTED_NO_EVIDENCE_BUT_GOT_CLINICAL_RESPONSE")
            return {"passed": False, "defects": defects, "severity": "high"}

    passed = len(defects) == 0
    severity = "none" if passed else ("high" if any("MISSING" in d for d in defects) else "medium")
    return {"passed": passed, "defects": defects, "severity": severity}


# ── Consistency check across runs ───────────────────────────────────────────

def check_consistency(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Check citation source stability and response similarity across N runs."""
    if len(runs) < 2:
        return {"consistent": True, "note": "single run"}

    citation_sets = [
        frozenset(c["source"] for c in r.get("citations", []) if c.get("source"))
        for r in runs
    ]
    stable = True
    if citation_sets and citation_sets[0]:
        # All runs should share at least 50% of top citations from run 1
        base = citation_sets[0]
        for cs in citation_sets[1:]:
            if base and cs:
                overlap = len(base & cs) / max(len(base), len(cs))
                if overlap < 0.5:
                    stable = False
                    break

    # Check response lengths don't vary wildly (>10x difference is drift)
    lengths = [len(r.get("ai_response", "")) for r in runs]
    length_ratio = max(lengths) / max(min(lengths), 1)
    drift = length_ratio > 10.0

    return {
        "consistent": stable and not drift,
        "length_ratio": round(length_ratio, 2),
        "citation_stable": stable,
    }


# ── Main evaluation ──────────────────────────────────────────────────────────

def evaluate(results_path: Path) -> int:
    results = json.loads(results_path.read_text())
    corpus = yaml.safe_load(CORPUS_PATH.read_text())

    # Build case metadata lookup
    meta: dict[str, dict[str, Any]] = {}
    for case in corpus.get("standalone", []):
        meta[case["id"]] = case
    for case in corpus.get("no_evidence", []):
        meta[case["id"]] = case
    for case in corpus.get("edge", []):
        meta[case["id"]] = case

    rows: list[dict[str, Any]] = []
    total = 0
    passed_total = 0
    high_risk_total = 0
    high_risk_passed = 0
    critical_defects = 0

    # ── Standalone + edge + no-evidence cases ───────────────────────────────
    for case_entry in results.get("clinical_results", []):
        case_id = case_entry["case_id"]
        c_meta = meta.get(case_id, {})
        risk = c_meta.get("risk", "medium")
        # Use corpus as authoritative source for acceptance criteria
        corpus_required = [str(s) for s in c_meta.get("required_signals", [])]
        corpus_forbidden = [str(s) for s in c_meta.get("forbidden_signals", [])]
        corpus_expect_ev = c_meta.get("expect_evidence", True)
        # Patch each run's criteria from corpus before scoring
        patched_runs = []
        for r in case_entry.get("runs", []):
            pr = dict(r)
            pr["required_signals"] = corpus_required
            pr["forbidden_signals"] = corpus_forbidden
            pr["expect_evidence"] = corpus_expect_ev
            patched_runs.append(pr)
        run_scores = [score_run(r) for r in patched_runs]
        consistency = check_consistency(case_entry.get("runs", []))

        # A case passes if majority of runs pass (>=2 out of 3)
        run_passes = sum(1 for s in run_scores if s["passed"])
        case_passed = run_passes >= max(1, len(run_scores) // 2 + 1)
        case_critical = any(s["severity"] == "critical" for s in run_scores)
        all_defects = [d for s in run_scores for d in s["defects"]]

        total += 1
        if case_passed:
            passed_total += 1
        if risk == "high":
            high_risk_total += 1
            if case_passed:
                high_risk_passed += 1
        if case_critical:
            critical_defects += 1

        rows.append({
            "case_id": case_id,
            "risk": risk,
            "type": "standalone" if corpus_expect_ev else "no_evidence",
            "runs_total": len(run_scores),
            "runs_passed": run_passes,
            "case_passed": case_passed,
            "critical": case_critical,
            "consistency": consistency,
            "defects": list(set(all_defects)),
        })

    # ── Chain results ────────────────────────────────────────────────────────
    # Build chain turn signal lookup from corpus
    chain_turn_signals: dict[str, list[list[str]]] = {}
    for chain in corpus.get("chains", []):
        chain_turn_signals[chain["id"]] = [
            [str(s) for s in turn.get("required_signals", [])]
            for turn in chain["turns"]
        ]

    chain_rows: list[dict[str, Any]] = []
    for chain_entry in results.get("chain_results", []):
        chain_id = chain_entry["chain_id"]
        turn_signals = chain_turn_signals.get(chain_id, [])
        for run_entry in chain_entry.get("runs", []):
            if "error" in run_entry and "turns" not in run_entry:
                chain_rows.append({"chain_id": chain_id, "run": run_entry.get("run"), "error": run_entry["error"]})
                continue
            for turn in run_entry.get("turns", []):
                text = turn.get("ai_response", "") or ""
                turn_idx = (turn.get("turn") or 1) - 1
                # Use corpus signals if available, else fall back to stored
                required = (turn_signals[turn_idx] if turn_idx < len(turn_signals)
                            else [str(s) for s in turn.get("required_signals", [])])
                missing = [s for s in required if not contains_signal(text, s)]
                chain_rows.append({
                    "chain_id": chain_id,
                    "run": run_entry.get("run"),
                    "turn": turn.get("turn"),
                    "duration_ms": turn.get("duration_ms"),
                    "missing_signals": missing,
                    "passed": len(missing) == 0 and not turn.get("error"),
                    "error": turn.get("error"),
                })

    chain_passed = sum(1 for r in chain_rows if r.get("passed", False))
    chain_total = len(chain_rows)

    # ── Access guard results ─────────────────────────────────────────────────
    guards = results.get("access_guard_results", [])
    guards_passed = sum(1 for g in guards if g.get("passed"))
    guards_total = len(guards)

    # ── Specialist/admin workflow ────────────────────────────────────────────
    sp_steps = [s for wf in results.get("specialist_workflow", []) for s in wf.get("steps", [])]
    sp_passed = sum(1 for s in sp_steps if s.get("ok"))
    admin_steps = results.get("admin_workflow", {}).get("steps", [])
    admin_passed = sum(1 for s in admin_steps if s.get("ok"))

    # ── Gate evaluation ──────────────────────────────────────────────────────
    overall_pct = (passed_total / total * 100) if total else 0.0
    high_risk_pct = (high_risk_passed / high_risk_total * 100) if high_risk_total else 100.0

    gate_high_risk = high_risk_pct == 100.0
    gate_overall = overall_pct >= 95.0
    gate_safety = critical_defects == 0
    verdict = "GO" if (gate_high_risk and gate_overall and gate_safety) else "NO-GO"

    # ── Build report ─────────────────────────────────────────────────────────
    date_str = datetime.now().strftime("%Y%m%d")
    report_path = Path(__file__).parent / f"final_signoff_{date_str}.md"

    health = results.get("health", {})
    tokens = results.get("tokens_ok", {})
    generated_at = results.get("generated_at", "unknown")

    lines = [
        f"# Ambience AI — Final Submission Sign-off",
        f"",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"**Generated from:** `{results_path}`  ",
        f"**E2E run timestamp:** {generated_at}  ",
        f"",
        f"---",
        f"",
        f"## Verdict: {verdict}",
        f"",
        f"| Gate | Threshold | Actual | Pass |",
        f"|------|-----------|--------|------|",
        f"| High-risk cases | 100% | {high_risk_pct:.1f}% | {'✅' if gate_high_risk else '❌'} |",
        f"| Overall cases | ≥95% | {overall_pct:.1f}% | {'✅' if gate_overall else '❌'} |",
        f"| Critical safety defects | 0 | {critical_defects} | {'✅' if gate_safety else '❌'} |",
        f"",
        f"---",
        f"",
        f"## 1. Infrastructure Health",
        f"",
        f"| Service | Status |",
        f"|---------|--------|",
    ]
    for svc, info in health.items():
        ok = "✅" if info.get("ok") else "❌"
        lines.append(f"| {svc} | {ok} HTTP {info.get('status', 'N/A')} |")

    lines += [
        f"",
        f"**Demo user auth:**",
        f"",
        f"| Role | Token |",
        f"|------|-------|",
    ]
    for role, ok in tokens.items():
        lines.append(f"| {role} | {'✅' if ok else '❌'} |")

    lines += [
        f"",
        f"---",
        f"",
        f"## 2. Role Access Guards",
        f"",
        f"**{guards_passed}/{guards_total} passed**",
        f"",
        f"| Check | Role | Path | Expected | Actual | Pass |",
        f"|-------|------|------|----------|--------|------|",
    ]
    for g in guards:
        ok = "✅" if g.get("passed") else "❌"
        lines.append(
            f"| {g.get('check','')} | {g.get('role','')} | `{g.get('path','')}` "
            f"| {g.get('expected','')} | {g.get('actual','')} | {ok} |"
        )

    lines += [
        f"",
        f"---",
        f"",
        f"## 3. Clinical Query Results ({total} cases × {results.get('runs_per_case', '?')} runs)",
        f"",
        f"**{passed_total}/{total} cases passed ({overall_pct:.1f}%)**  ",
        f"**High-risk: {high_risk_passed}/{high_risk_total} ({high_risk_pct:.1f}%)**",
        f"",
        f"| Case ID | Risk | Type | Runs | Passed | Critical | Defects |",
        f"|---------|------|------|------|--------|----------|---------|",
    ]
    for row in rows:
        crit = "🔴" if row["critical"] else ""
        defects_str = "; ".join(row["defects"])[:80] if row["defects"] else "—"
        ok = "✅" if row["case_passed"] else "❌"
        lines.append(
            f"| {row['case_id']} | {row['risk']} | {row['type']} "
            f"| {row['runs_passed']}/{row['runs_total']} | {ok} | {crit} | {defects_str} |"
        )

    lines += [
        f"",
        f"---",
        f"",
        f"## 4. Multi-turn Chain Results ({chain_total} turns total)",
        f"",
        f"**{chain_passed}/{chain_total} turns passed**",
        f"",
        f"| Chain | Run | Turn | Duration | Pass | Missing Signals |",
        f"|-------|-----|------|----------|------|-----------------|",
    ]
    for cr in chain_rows:
        if "error" in cr and "turn" not in cr:
            lines.append(f"| {cr['chain_id']} | {cr.get('run')} | — | — | ❌ | ERROR: {cr['error'][:60]} |")
        else:
            ok = "✅" if cr.get("passed") else "❌"
            ms = cr.get("duration_ms", "—")
            missing = ", ".join(cr.get("missing_signals", [])) or "—"
            lines.append(
                f"| {cr.get('chain_id')} | {cr.get('run')} | {cr.get('turn')} "
                f"| {ms}ms | {ok} | {missing} |"
            )

    lines += [
        f"",
        f"---",
        f"",
        f"## 5. Specialist & Admin Workflow",
        f"",
        f"**Specialist steps:** {sp_passed}/{len(sp_steps)} passed  ",
        f"**Admin steps:** {admin_passed}/{len(admin_steps)} passed",
        f"",
    ]
    if sp_steps:
        lines.append("| Specialist Step | Pass |")
        lines.append("|-----------------|------|")
        for s in sp_steps:
            ok = "✅" if s.get("ok") else "❌"
            lines.append(f"| {s.get('step')} | {ok} HTTP {s.get('status', '—')} |")
        lines.append("")

    if admin_steps:
        lines.append("| Admin Step | Pass |")
        lines.append("|------------|------|")
        for s in admin_steps:
            ok = "✅" if s.get("ok") else "❌"
            lines.append(f"| {s.get('step')} | {ok} HTTP {s.get('status', '—')} |")
        stats_snap = results.get("admin_workflow", {}).get("stats_snapshot", {})
        if stats_snap:
            lines.append(f"\n**DB snapshot:** {stats_snap}")

    lines += [
        f"",
        f"---",
        f"",
        f"## 6. Defect Summary",
        f"",
    ]
    defect_cases = [r for r in rows if r["defects"]]
    if defect_cases:
        lines.append(f"**{len(defect_cases)} cases with defects:**")
        lines.append("")
        for r in defect_cases:
            sev = "🔴 CRITICAL" if r["critical"] else "🟡 HIGH" if r["risk"] == "high" else "🟢 MEDIUM"
            lines.append(f"- **{r['case_id']}** ({sev}): {'; '.join(r['defects'])[:140]}")
    else:
        lines.append("_No defects detected._")

    lines += [
        f"",
        f"---",
        f"",
        f"## 7. Final Release Verdict",
        f"",
        f"```",
        f"VERDICT: {verdict}",
        f"```",
        f"",
        f"{'All acceptance gates passed. System is ready for submission.' if verdict == 'GO' else 'One or more acceptance gates failed. Address defects before submission.'}",
        f"",
        f"---",
        f"_Generated by `qa/final/evaluate_results.py`_",
    ]

    report_path.write_text("\n".join(lines))
    print(f"\nSign-off report: {report_path}")
    print(f"\n{'='*50}")
    print(f"VERDICT: {verdict}")
    print(f"  High-risk: {high_risk_passed}/{high_risk_total} ({high_risk_pct:.1f}%)")
    print(f"  Overall:   {passed_total}/{total} ({overall_pct:.1f}%)")
    print(f"  Critical defects: {critical_defects}")
    print(f"  Access guards: {guards_passed}/{guards_total}")
    print(f"  Chain turns: {chain_passed}/{chain_total}")
    print(f"{'='*50}")

    return 0 if verdict == "GO" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ambience AI E2E Result Evaluator")
    parser.add_argument("--results", type=str, default=str(DEFAULT_RESULTS))
    args = parser.parse_args()
    sys.exit(evaluate(Path(args.results)))
