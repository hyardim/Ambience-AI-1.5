#!/usr/bin/env python3
"""
Final Submission Live E2E Harness
==================================
Drives the full GP -> AI -> Specialist -> Admin workflow through real
backend endpoints. Outputs structured JSON results for evaluate_results.py.

Usage:
  python qa/final/run_live_e2e.py [--runs N] [--out DIR] [--base URL]

Defaults:
  --runs  3
  --out   qa/final/results/
  --base  http://localhost:8000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml

BASE_URL = "http://localhost:8000"
TIMEOUT = 120.0
STREAM_CHUNK_LIMIT = 8192 * 10  # 80 KB max streamed response

CREDENTIALS = {
    "gp":         {"email": "gp@example.com",         "password": "Password123"},
    "specialist": {"email": "specialist@example.com", "password": "Password123"},
    "admin":      {"email": "admin@example.com",       "password": "Password123"},
}


# ── Auth helpers ────────────────────────────────────────────────────────────

async def login(client: httpx.AsyncClient, role: str) -> str:
    creds = CREDENTIALS[role]
    # Endpoint uses OAuth2 form data (username/password), not JSON
    r = await client.post(
        "/auth/login",
        data={"username": creds["email"], "password": creds["password"]},
    )
    r.raise_for_status()
    return r.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _post_with_retry(
    client: httpx.AsyncClient,
    path: str,
    *,
    json: Any = None,
    data: Any = None,
    headers: dict[str, str] | None = None,
    max_retries: int = 3,
    timeout: float = 30.0,
) -> httpx.Response:
    """POST with automatic backoff on 429 rate-limit responses."""
    for attempt in range(max_retries):
        r = await client.post(path, json=json, data=data, headers=headers, timeout=timeout)
        if r.status_code != 429:
            return r
        try:
            detail = r.json().get("detail", "")
            wait = int(re.search(r"(\d+)\s+se", detail).group(1)) + 2  # type: ignore[union-attr]
        except Exception:
            wait = 60
        print(f"        [rate-limit] waiting {wait}s before retry...")
        await asyncio.sleep(wait)
    return r  # return last response even if still 429


# ── Health check ─────────────────────────────────────────────────────────────

async def health_check(client: httpx.AsyncClient) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for path, name in [("/health", "backend")]:
        try:
            r = await client.get(path, timeout=10.0)
            results[name] = {"status": r.status_code, "ok": r.status_code == 200}
        except Exception as exc:
            results[name] = {"status": None, "ok": False, "error": str(exc)}
    return results


# ── Clinical query via GP chat stream ────────────────────────────────────────

async def _poll_for_ai_response(
    client: httpx.AsyncClient,
    chat_id: int,
    token: str,
    prev_msg_count: int,
    poll_interval: float = 1.0,
) -> tuple[str, list[Any]]:
    """Poll GET /chats/{id} until a new AI message with is_generating=False appears.

    Much more reliable than SSE for programmatic use — avoids pub/sub replay issues
    in multi-turn chains.
    """
    headers = auth_headers(token)
    deadline = time.perf_counter() + TIMEOUT
    while time.perf_counter() < deadline:
        await asyncio.sleep(poll_interval)
        try:
            r = await client.get(f"/chats/{chat_id}", headers=headers, timeout=15.0)
            if r.status_code != 200:
                continue
            data = r.json()
            messages = data.get("messages", [])
            new_ai = [
                m for m in messages[prev_msg_count:]
                if m.get("sender") == "ai" and not m.get("is_generating", True)
            ]
            if new_ai:
                last = new_ai[-1]
                text = last.get("content", "") or ""
                raw_citations = last.get("citations") or []
                citations = [
                    {
                        "source": (
                            c.get("source_name")
                            or c.get("metadata", {}).get("title")
                            or c.get("title")
                            or c.get("source", "")
                        ),
                        "score": (
                            c.get("metadata", {}).get("rerank_score")
                            or c.get("score")
                        ),
                    }
                    for c in raw_citations
                ]
                return text.strip(), citations
        except Exception:
            pass
    return "", []


async def _get_message_count(
    client: httpx.AsyncClient, chat_id: int, token: str
) -> int:
    """Get current number of messages in a chat."""
    try:
        r = await client.get(f"/chats/{chat_id}", headers=auth_headers(token), timeout=10.0)
        return len(r.json().get("messages", []))
    except Exception:
        return 0


async def run_clinical_query(
    client: httpx.AsyncClient,
    gp_token: str,
    prompt: str,
    specialty: str,
    run_id: int,
) -> dict[str, Any]:
    """Create chat, send message, poll for AI response."""
    result: dict[str, Any] = {
        "run": run_id,
        "prompt": prompt[:120],
        "specialty": specialty,
        "chat_id": None,
        "ai_response": "",
        "citations": [],
        "status_code": None,
        "error": None,
        "duration_ms": None,
    }
    headers = auth_headers(gp_token)
    t0 = time.perf_counter()
    try:
        # 1. Create new chat
        r = await _post_with_retry(
            client,
            "/chats/",
            json={
                "title": f"QA run {run_id}",
                "specialty": specialty,
                "severity": "medium",
                "patient_age": 60,
                "patient_gender": "male",
            },
            headers=headers,
        )
        r.raise_for_status()
        chat_id = r.json()["id"]
        result["chat_id"] = chat_id

        # 2. Note message count before sending
        prev_count = await _get_message_count(client, chat_id, gp_token)

        # 3. Send message
        r2 = await _post_with_retry(
            client,
            f"/chats/{chat_id}/message",
            json={"content": prompt},
            headers=headers,
        )
        r2.raise_for_status()
        result["status_code"] = r2.status_code

        # 4. Poll for AI response
        ai_text, citations = await _poll_for_ai_response(
            client, chat_id, gp_token, prev_count + 1
        )
        result["ai_response"] = ai_text
        result["citations"] = citations

        # 5. Submit for specialist review
        r3 = await _post_with_retry(
            client, f"/chats/{chat_id}/submit", headers=headers
        )
        if r3.status_code not in (200, 204):
            result["submit_error"] = f"submit returned {r3.status_code}"

    except httpx.HTTPStatusError as exc:
        result["error"] = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
        result["status_code"] = exc.response.status_code
    except Exception as exc:
        result["error"] = str(exc)

    result["duration_ms"] = round((time.perf_counter() - t0) * 1000)
    return result


# ── Specialist workflow ───────────────────────────────────────────────────────

async def run_specialist_workflow(
    client: httpx.AsyncClient,
    sp_token: str,
    chat_id: int,
) -> dict[str, Any]:
    headers = auth_headers(sp_token)
    log: dict[str, Any] = {"chat_id": chat_id, "steps": []}

    async def step(name: str, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            r = await client.request(method, path, headers=headers, timeout=30.0, **kwargs)
            entry = {"step": name, "status": r.status_code, "ok": r.status_code < 300}
            log["steps"].append(entry)
            return r.json() if r.status_code < 300 else {}
        except Exception as exc:
            log["steps"].append({"step": name, "error": str(exc), "ok": False})
            return {}

    # Get specialist's own user ID first
    me = await step("get_profile", "GET", "/auth/me")
    specialist_id = me.get("id")
    if not specialist_id:
        log["steps"].append({"step": "assign", "error": "Could not get specialist user ID", "ok": False})
        return log

    await step("assign", "POST", f"/specialist/chats/{chat_id}/assign", json={"specialist_id": specialist_id})
    await step(
        "approve",
        "POST",
        f"/specialist/chats/{chat_id}/review",
        json={"action": "approve", "feedback": "Reviewed and approved by specialist. AI recommendation confirmed."},
    )
    return log


# ── Admin workflow ────────────────────────────────────────────────────────────

async def run_admin_workflow(
    client: httpx.AsyncClient,
    admin_token: str,
) -> dict[str, Any]:
    headers = auth_headers(admin_token)
    log: dict[str, Any] = {"steps": []}

    async def step(name: str, path: str) -> Any:
        try:
            r = await client.get(path, headers=headers, timeout=30.0)
            entry = {"step": name, "status": r.status_code, "ok": r.status_code == 200}
            log["steps"].append(entry)
            return r.json() if r.status_code == 200 else None
        except Exception as exc:
            log["steps"].append({"step": name, "error": str(exc), "ok": False})
            return None

    stats = await step("admin_stats", "/admin/stats")
    if stats:
        log["stats_snapshot"] = {
            "total_chats": stats.get("total_chats"),
            "total_users": stats.get("total_users"),
        }
    await step("admin_users_list", "/admin/users?limit=5")
    await step("admin_chats_list", "/admin/chats?limit=5")
    await step("admin_rag_status", "/admin/rag/status")
    return log


# ── Role-access guard checks ─────────────────────────────────────────────────

async def run_access_guards(
    client: httpx.AsyncClient,
    tokens: dict[str, str],
) -> list[dict[str, Any]]:
    """Verify role boundaries are enforced."""
    checks = [
        # GP cannot access specialist queue
        ("gp_vs_specialist_queue", "gp", "GET", "/specialist/queue", 403),
        # GP cannot access admin
        ("gp_vs_admin_stats", "gp", "GET", "/admin/stats", 403),
        # Specialist cannot access admin
        ("specialist_vs_admin_stats", "specialist", "GET", "/admin/stats", 403),
        # Admin can access specialist queue
        ("admin_vs_specialist_queue", "admin", "GET", "/specialist/queue", 200),
        # Admin can access admin stats
        ("admin_vs_admin_stats", "admin", "GET", "/admin/stats", 200),
    ]
    results = []
    for name, role, method, path, expected_status in checks:
        try:
            r = await client.request(
                method, path, headers=auth_headers(tokens[role]), timeout=10.0
            )
            passed = r.status_code == expected_status
        except Exception as exc:
            results.append({"check": name, "passed": False, "error": str(exc)})
            continue
        results.append({
            "check": name,
            "role": role,
            "path": path,
            "expected": expected_status,
            "actual": r.status_code,
            "passed": passed,
        })
    return results


# ── Main harness ─────────────────────────────────────────────────────────────

async def main(runs: int, out_dir: Path, base_url: str) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    corpus_path = Path(__file__).parent / "corpus.yaml"
    corpus = yaml.safe_load(corpus_path.read_text())

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "runs_per_case": runs,
        "health": {},
        "tokens_ok": {},
        "clinical_results": [],
        "chain_results": [],
        "access_guard_results": [],
        "specialist_workflow": [],
        "admin_workflow": {},
    }

    async with httpx.AsyncClient(base_url=base_url, timeout=TIMEOUT) as client:
        # ── Health ──────────────────────────────────────────────────────────
        print("[ 1/6 ] Health checks...")
        report["health"] = await health_check(client)
        # Also check RAG directly
        try:
            rag_r = httpx.get("http://localhost:8001/health", timeout=10.0)
            report["health"]["rag"] = {"status": rag_r.status_code, "ok": rag_r.status_code == 200}
        except Exception as exc:
            report["health"]["rag"] = {"status": None, "ok": False, "error": str(exc)}
        for svc, res in report["health"].items():
            status = "OK" if res["ok"] else "FAIL"
            print(f"        {svc}: {status} (HTTP {res.get('status')})")

        # ── Auth ────────────────────────────────────────────────────────────
        print("[ 2/6 ] Authenticating demo users...")
        tokens: dict[str, str] = {}
        for role in ("gp", "specialist", "admin"):
            try:
                tokens[role] = await login(client, role)
                report["tokens_ok"][role] = True
                print(f"        {role}: OK")
            except Exception as exc:
                report["tokens_ok"][role] = False
                print(f"        {role}: FAIL ({exc})")

        if not tokens.get("gp"):
            print("FATAL: cannot authenticate GP — aborting clinical runs")
            _save(report, out_dir)
            return 1

        # ── Role-access guards ───────────────────────────────────────────────
        print("[ 3/6 ] Role access guard checks...")
        report["access_guard_results"] = await run_access_guards(client, tokens)
        passed = sum(1 for c in report["access_guard_results"] if c.get("passed"))
        total = len(report["access_guard_results"])
        print(f"        {passed}/{total} access guard checks passed")

        # ── Standalone clinical queries ──────────────────────────────────────
        print(f"[ 4/6 ] Standalone clinical queries ({runs} runs each)...")
        all_cases = (
            corpus.get("standalone", [])
            + corpus.get("no_evidence", [])
            + corpus.get("edge", [])
        )
        submitted_chat_ids: list[int] = []
        for case in all_cases:
            case_results = []
            for run_n in range(1, runs + 1):
                res = await run_clinical_query(
                    client,
                    tokens["gp"],
                    case["prompt"],
                    case.get("specialty", "rheumatology"),
                    run_n,
                )
                res["case_id"] = case["id"]
                res["expect_evidence"] = case.get("expect_evidence", True)
                res["required_signals"] = case.get("required_signals", [])
                res["forbidden_signals"] = case.get("forbidden_signals", [])
                case_results.append(res)
                if res.get("chat_id"):
                    submitted_chat_ids.append(res["chat_id"])
                err_tag = f" ERR:{res['error'][:60]}" if res.get("error") else ""
                print(
                    f"        {case['id']} run{run_n}: "
                    f"{res['duration_ms']}ms "
                    f"citations={len(res['citations'])}"
                    f"{err_tag}"
                )
                # Pace between runs: rate limit is 60 req/min; 4 reqs per case → 1 per 4s min
                if run_n < runs:
                    await asyncio.sleep(1)
            report["clinical_results"].append(
                {"case_id": case["id"], "runs": case_results}
            )

        # ── Multi-turn chains ────────────────────────────────────────────────
        print(f"[ 4b/6] Multi-turn chains ({runs} runs each)...")
        for chain in corpus.get("chains", []):
            chain_entry = {"chain_id": chain["id"], "runs": []}
            for run_n in range(1, runs + 1):
                # Create one chat per chain run, send each turn
                turn_results = []
                headers_gp = auth_headers(tokens["gp"])
                specialty = chain.get("specialty", "rheumatology")
                # Create chat
                try:
                    r = await _post_with_retry(
                        client,
                        "/chats/",
                        json={
                            "title": f"Chain {chain['id']} run{run_n}",
                            "specialty": specialty,
                            "severity": "medium",
                            "patient_age": 65,
                            "patient_gender": "female",
                        },
                        headers=headers_gp,
                    )
                    r.raise_for_status()
                    chain_chat_id = r.json()["id"]
                except Exception as exc:
                    chain_entry["runs"].append({"run": run_n, "error": str(exc)})
                    continue

                for turn_idx, turn in enumerate(chain["turns"]):
                    t0 = time.perf_counter()
                    ai_text = ""
                    citations: list[Any] = []
                    err = None
                    try:
                        gp_tok = tokens["gp"]
                        # Get current message count before sending
                        prev_cnt = await _get_message_count(client, chain_chat_id, gp_tok)
                        # Send turn message
                        r_msg = await _post_with_retry(
                            client, f"/chats/{chain_chat_id}/message",
                            json={"content": turn["prompt"]}, headers=headers_gp,
                        )
                        r_msg.raise_for_status()
                        # Poll for new AI response
                        ai_text, citations = await _poll_for_ai_response(
                            client, chain_chat_id, gp_tok, prev_cnt + 1
                        )
                    except Exception as exc:
                        err = str(exc)
                    dur = round((time.perf_counter() - t0) * 1000)
                    turn_results.append({
                        "turn": turn_idx + 1,
                        "prompt": turn["prompt"][:80],
                        "ai_response": ai_text.strip() if isinstance(ai_text, str) else "",
                        "citations": [c.get("source", "") for c in citations] if citations else [],
                        "required_signals": turn.get("required_signals", []),
                        "duration_ms": dur,
                        "error": err,
                    })
                    print(f"        {chain['id']} run{run_n} turn{turn_idx+1}: {dur}ms")

                # Submit chain chat
                try:
                    await client.post(
                        f"/chats/{chain_chat_id}/submit",
                        headers=headers_gp,
                        timeout=30.0,
                    )
                    submitted_chat_ids.append(chain_chat_id)
                except Exception:
                    pass
                chain_entry["runs"].append({"run": run_n, "turns": turn_results})
            report["chain_results"].append(chain_entry)

        # ── Specialist workflow ──────────────────────────────────────────────
        print("[ 5/6 ] Specialist workflow...")
        if tokens.get("specialist") and submitted_chat_ids:
            # Only drive workflow on first submitted chat (to avoid flooding)
            chat_to_review = submitted_chat_ids[0]
            sp_log = await run_specialist_workflow(
                client, tokens["specialist"], chat_to_review
            )
            report["specialist_workflow"].append(sp_log)
            passed_steps = sum(1 for s in sp_log["steps"] if s.get("ok"))
            print(f"        {passed_steps}/{len(sp_log['steps'])} steps passed")
        else:
            print("        SKIP (no specialist token or no submitted chats)")

        # ── Admin workflow ───────────────────────────────────────────────────
        print("[ 6/6 ] Admin workflow...")
        if tokens.get("admin"):
            report["admin_workflow"] = await run_admin_workflow(
                client, tokens["admin"]
            )
            passed_steps = sum(
                1 for s in report["admin_workflow"].get("steps", []) if s.get("ok")
            )
            total_steps = len(report["admin_workflow"].get("steps", []))
            print(f"        {passed_steps}/{total_steps} steps passed")
        else:
            print("        SKIP (no admin token)")

    _save(report, out_dir)
    print(f"\nResults saved to {out_dir}/e2e_results.json")
    return 0


def _save(report: dict[str, Any], out_dir: Path) -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"e2e_results_{ts}.json"
    out_path.write_text(json.dumps(report, indent=2, default=str))
    # Also write latest symlink-style copy for evaluate_results.py
    (out_dir / "e2e_results.json").write_text(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ambience AI Live E2E Harness")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--out", type=str, default="qa/final/results")
    parser.add_argument("--base", type=str, default=BASE_URL)
    args = parser.parse_args()

    exit_code = asyncio.run(main(args.runs, Path(args.out), args.base))
    sys.exit(exit_code)
