"""Verify a request against a compiled policy."""

import json

GENERIC = [
    (
        "Can I expense a $75 software license?",
        "Yes, with a receipt. The license is for my own work.",
    ),
    (
        "Is a $200 client dinner allowed?",
        "It was with a client and I have an itemized receipt.",
    ),
    (
        "Can I submit travel without receipts?",
        "The trip was pre-approved, but I no longer have the receipts.",
    ),
]


def render() -> None:
    import streamlit as st

    from streamlit_ui import api, cache, components
    from streamlit_ui.api import ApiError

    st.header("Verify")
    st.caption("Check a request and a proposed answer against a policy.")

    try:
        policies = cache.cached_policies(api.base_url())
    except ApiError as exc:
        st.error(str(exc))
        return

    if not policies:
        st.info("No policies yet. Upload one on the Policies page.")
        return

    ordered = sorted(policies, key=lambda p: 0 if _status(p) in ("compiled", "active") else 1)
    labels = { _label(p): p for p in ordered }
    selected_label = st.selectbox("Policy", list(labels), key="verify_policy")
    policy = labels[selected_label]
    policy_id = str(policy.get("id"))

    try:
        full = api.get_policy(policy_id)
    except ApiError:
        full = policy

    with st.popover("Examples"):
        samples = _examples(full)
        for index, (question, answer) in enumerate(samples):
            st.caption(question)
            if st.button("Use this example", key=f"ex_{policy_id}_{index}"):
                st.session_state.verify_request = question
                st.session_state.verify_answer = answer
                st.rerun()

    question = st.text_area("Request", key="verify_request", height=120)
    answer = st.text_area("Context / proposed answer (optional)", key="verify_answer", height=120)
    with st.expander("Trusted facts (optional)"):
        st.caption("JSON from a system of record, e.g. {\"has_manager_approval\": true}. Overrides the text.")
        facts_text = st.text_area("Facts JSON", key="verify_facts", height=80, label_visibility="collapsed")

    if st.button("Verify", type="primary", key="verify_btn"):
        facts, facts_error = _parse_facts(facts_text)
        if not (question or "").strip():
            st.error("Enter a request.")
        elif facts_error:
            st.error(facts_error)
        else:
            with st.spinner("Verifying"):
                try:
                    result = api.verify(policy_id, question.strip(), (answer or "").strip(), facts)
                except ApiError as exc:
                    st.error(str(exc))
                    result = None
            if result is not None:
                st.session_state["verify_result"] = result
                st.session_state["verify_result_policy"] = full
                cache.clear()

    result = st.session_state.get("verify_result")
    shown_policy = st.session_state.get("verify_result_policy") or full
    if result and str(shown_policy.get("id")) == policy_id:
        components.render_result(result, shown_policy)


def _parse_facts(text: str | None) -> tuple[dict | None, str | None]:
    if not (text or "").strip():
        return None, None
    try:
        facts = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"Trusted facts are not valid JSON: {exc.msg}"
    if not isinstance(facts, dict):
        return None, "Trusted facts must be a JSON object."
    return facts, None


def _status(policy: dict) -> str:
    return str(policy.get("status") or "").lower()


def _label(policy: dict) -> str:
    return f"{policy.get('name') or 'Untitled'}  ·  {policy.get('status') or 'unknown'}"


def _examples(policy: dict) -> list[tuple[str, str]]:
    samples = []
    for item in policy.get("examples") or []:
        if isinstance(item, dict) and item.get("question"):
            samples.append((item["question"], item.get("explanation") or item.get("answer") or ""))
    return samples or GENERIC


if __name__ == "__main__":
    render()
