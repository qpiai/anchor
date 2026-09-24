"""Shared result widgets."""

from __future__ import annotations

import streamlit as st

VERDICTS = ("VALID", "INVALID", "NEEDS_CLARIFICATION", "ERROR")


def verdict_of(payload: dict) -> str:
    raw = payload.get("result") or payload.get("verification_result") or "ERROR"
    text = str(raw).upper()
    if text in VERDICTS:
        return text
    if text in ("NEEDS CLARIFICATION", "NEEDS-CLARIFICATION"):
        return "NEEDS_CLARIFICATION"
    return "ERROR"


def badge(verdict: str) -> None:
    label = verdict.replace("_", " ")
    st.markdown(
        f'<span class="verdict verdict-{verdict}">{label}</span>',
        unsafe_allow_html=True,
    )


def render_result(payload: dict, policy: dict | None = None) -> None:
    details = payload.get("details") or None
    verdict = verdict_of(payload)
    badge(verdict)
    explanation = payload.get("explanation") or ""
    if explanation:
        st.write(explanation)

    st.subheader("Facts")
    _facts(payload.get("extracted_variables") or {}, details)

    if verdict == "NEEDS_CLARIFICATION":
        suggestions = payload.get("suggestions") or []
        st.subheader("Clarifying questions")
        if suggestions:
            for item in suggestions:
                st.markdown(f"- {item}")
        else:
            st.caption("The policy needs more information, but no questions were returned.")

    rules = (policy or {}).get("rules") or []
    _rules(details, rules)
    _footer(details)


def _facts(extracted: dict, details: dict | None) -> None:
    details = details or {}
    confidence = details.get("confidence") or {}
    sources = details.get("sources") or {}
    missing = set(details.get("missing_mandatory_vars") or [])
    names = list(dict.fromkeys([*extracted.keys(), *missing]))
    if not names:
        st.caption("No facts extracted.")
        return
    for name in names:
        value = extracted.get(name, None)
        is_missing = name in missing or value in ("MISSING_MANDATORY", None, "")
        conf = confidence.get(name)
        source = sources.get(name) or "n/a"
        c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
        c1.markdown(f"**{name}**" + (" · missing" if is_missing else ""))
        c2.write("missing" if is_missing else value)
        if isinstance(conf, (int, float)):
            c3.progress(min(max(float(conf), 0.0), 1.0), text=f"{float(conf):.0%}")
        else:
            c3.caption("n/a")
        c4.caption(str(source))


def _rules(details: dict | None, policy_rules: list) -> None:
    results = (details or {}).get("rule_results") or []
    if not results:
        return
    by_id = {str(rule.get("id")): rule for rule in policy_rules if isinstance(rule, dict)}
    st.subheader("Rules")
    rows = []
    for item in results:
        if not isinstance(item, dict):
            continue
        rule_id = str(item.get("rule_id") or "")
        rule = by_id.get(rule_id, {})
        rows.append(
            {
                "Rule": rule_id,
                "Description": item.get("description") or rule.get("description") or "",
                "Result": item.get("result") or "",
            }
        )
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")


def _footer(details: dict | None) -> None:
    if not details:
        return
    latency = details.get("latency_ms") or {}
    extract = _ms(latency.get("extract"))
    verify = _ms(latency.get("verify"))
    total = _ms(latency.get("total"))
    extractor = details.get("extractor") or "unknown"
    model = details.get("model") or "unknown"
    st.caption(
        f"{extractor} · {model} · extract {extract} ms / verify {verify} ms / total {total} ms"
    )
    if details.get("fallback_used"):
        reason = details.get("fallback_reason")
        st.warning("Fallback used" + (f": {reason}" if reason else ""))
    flags = details.get("flags") or {}
    if flags.get("out_of_scope"):
        st.warning("Out of scope")
    if flags.get("injection_suspected"):
        st.warning("Injection suspected")


def _ms(value) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.0f}"
    return "n/a"
