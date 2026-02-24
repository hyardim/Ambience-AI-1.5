from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class RouteDecision:
    target: str
    reason: str


def _estimate_tokens(text: str) -> int:
    # Rough heuristic: 1 token ~= 4 chars for English clinical text
    return max(1, len(text) // 4)


def _complexity_score(text: str) -> int:
    lowered = text.lower()
    score = 0

    high_value_terms = [
        "differential diagnosis",
        "contraindication",
        "drug interaction",
        "comorbidity",
        "refractory",
        "autoimmune",
        "red flag",
        "urgent",
        "escalation",
        "rare",
        "multisystem",
        "pregnancy",
        "renal impairment",
        "hepatotoxic",
    ]

    for term in high_value_terms:
        if term in lowered:
            score += 1

    if "?" in text and text.count("?") >= 2:
        score += 1

    # Longer prompts tend to be clinically richer/complex
    if len(text) >= 1600:
        score += 2
    elif len(text) >= 900:
        score += 1

    return score


def choose_model_target(prompt: str) -> RouteDecision:
    force_target = os.getenv("MODEL_ROUTER_FORCE_TARGET", "auto").strip().lower()
    if force_target in {"local", "cloud"}:
        return RouteDecision(
            target=force_target,
            reason=f"forced:{force_target}",
        )

    estimated_tokens = _estimate_tokens(prompt)
    complexity = _complexity_score(prompt)

    cloud_min_tokens = int(os.getenv("MODEL_ROUTER_CLOUD_MIN_TOKENS", "500"))
    cloud_min_complexity = int(os.getenv("MODEL_ROUTER_CLOUD_MIN_COMPLEXITY", "2"))

    if estimated_tokens >= cloud_min_tokens or complexity >= cloud_min_complexity:
        return RouteDecision(
            target="cloud",
            reason=f"auto:tokens={estimated_tokens},complexity={complexity}",
        )

    return RouteDecision(
        target="local",
        reason=f"auto:tokens={estimated_tokens},complexity={complexity}",
    )


def _auth_headers(api_key: str | None) -> dict[str, str]:
    if not api_key:
        return {"Content-Type": "application/json"}
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }


def _call_tgi(endpoint: str, prompt: str, api_key: str | None) -> str:
    max_new_tokens = int(os.getenv("MODEL_MAX_NEW_TOKENS", "512"))
    temperature = float(os.getenv("MODEL_TEMPERATURE", "0.1"))
    timeout_seconds = float(os.getenv("MODEL_TIMEOUT_SECONDS", "60"))

    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": max_new_tokens,
            "temperature": temperature,
            "do_sample": temperature > 0,
        },
    }

    response = requests.post(
        endpoint,
        json=payload,
        headers=_auth_headers(api_key),
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()

    if isinstance(data, dict) and isinstance(data.get("generated_text"), str):
        return data["generated_text"].strip()

    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict) and isinstance(first.get("generated_text"), str):
            return first["generated_text"].strip()

    raise ValueError("Unexpected TGI response format")


def _call_openai_compatible(
    endpoint: str,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    api_key: str | None,
) -> str:
    max_tokens = int(os.getenv("MODEL_MAX_NEW_TOKENS", "512"))
    temperature = float(os.getenv("MODEL_TEMPERATURE", "0.1"))
    timeout_seconds = float(os.getenv("MODEL_TIMEOUT_SECONDS", "60"))

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    response = requests.post(
        endpoint,
        json=payload,
        headers=_auth_headers(api_key),
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()

    choices = data.get("choices") if isinstance(data, dict) else None
    if isinstance(choices, list) and choices:
        first = choices[0]
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            return content.strip()

    raise ValueError("Unexpected OpenAI-compatible response format")


def _build_prompt(user_message: str, chat_history: list[dict[str, str]]) -> str:
    system_prompt = os.getenv(
        "MODEL_SYSTEM_PROMPT",
        (
            "You are an NHS clinical decision support assistant specialized in "
            "neurology and rheumatology. Provide concise, evidence-aligned guidance, "
            "include uncertainty where relevant, and recommend escalation for red flags."
        ),
    )

    history_lines: list[str] = []
    for item in chat_history[-8:]:
        role = item.get("role", "user")
        content = item.get("content", "")
        history_lines.append(f"{role.upper()}: {content}")

    history_text = "\n".join(history_lines)

    return (
        f"System:\n{system_prompt}\n\n"
        f"Conversation so far:\n{history_text}\n\n"
        f"Latest user query:\n{user_message}\n\n"
        "Respond in clear clinical language."
    )


def _invoke_target(
    target: str,
    prompt: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    if target == "cloud":
        endpoint = os.getenv("MODEL_CLOUD_URL", "").strip()
        api_style = os.getenv("MODEL_CLOUD_API_STYLE", "tgi").strip().lower()
        api_key = os.getenv("MODEL_CLOUD_API_KEY", "").strip() or None
        model_name = os.getenv("MODEL_CLOUD_NAME", "med42-80b")
    else:
        endpoint = os.getenv("MODEL_LOCAL_URL", "http://host.docker.internal:80/generate").strip()
        api_style = os.getenv("MODEL_LOCAL_API_STYLE", "tgi").strip().lower()
        api_key = os.getenv("MODEL_LOCAL_API_KEY", "").strip() or None
        model_name = os.getenv("MODEL_LOCAL_NAME", "med42-7b")

    if not endpoint:
        raise ValueError(f"No endpoint configured for target={target}")

    if api_style == "openai":
        return _call_openai_compatible(
            endpoint=endpoint,
            model_name=model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            api_key=api_key,
        )

    return _call_tgi(endpoint=endpoint, prompt=prompt, api_key=api_key)


def generate_ai_response(
    user_message: str,
    chat_history: list[dict[str, str]],
) -> tuple[str, str, str]:
    """
    Returns: (content, model_used, decision_reason)
    """
    prompt = _build_prompt(user_message=user_message, chat_history=chat_history)

    decision = choose_model_target(prompt)

    system_prompt = os.getenv(
        "MODEL_SYSTEM_PROMPT",
        "You are an NHS clinical decision support assistant.",
    )

    try:
        content = _invoke_target(
            target=decision.target,
            prompt=prompt,
            system_prompt=system_prompt,
            user_prompt=user_message,
        )
        return content, decision.target, decision.reason
    except Exception as first_error:
        fallback_target = "local" if decision.target == "cloud" else "cloud"
        try:
            content = _invoke_target(
                target=fallback_target,
                prompt=prompt,
                system_prompt=system_prompt,
                user_prompt=user_message,
            )
            return (
                content,
                fallback_target,
                f"{decision.reason};fallback_from={decision.target};error={first_error}",
            )
        except Exception:
            safe_fallback = (
                "I’m unable to reach the configured AI model endpoints right now. "
                "Please retry in a moment or escalate this query for manual review."
            )
            return safe_fallback, "none", f"{decision.reason};both_endpoints_failed"
