"""Recent verifications for one policy."""


def render() -> None:
    import streamlit as st

    from streamlit_ui import api, cache, components
    from streamlit_ui.api import ApiError

    st.header("History")

    try:
        policies = cache.cached_policies(api.base_url())
    except ApiError as exc:
        st.error(str(exc))
        return

    if not policies:
        st.info("No policies yet.")
        return

    labels = {_label(p): p for p in policies}
    choice = st.selectbox("Policy", list(labels), key="history_policy")
    policy = labels[choice]
    policy_id = str(policy.get("id"))

    try:
        rows = cache.cached_verifications(api.base_url(), policy_id)
    except ApiError as exc:
        st.error(str(exc))
        return

    if not rows:
        st.caption("No verifications yet.")
        return

    st.dataframe([_summary(row) for row in rows], hide_index=True, width="stretch")
    options = {_option(row): row for row in rows}
    picked = st.selectbox("Open verification", list(options), key="history_row")
    item = options[picked]

    try:
        full = api.get_policy(policy_id)
    except ApiError:
        full = policy
    components.render_result(item, full)


def _label(policy: dict) -> str:
    return f"{policy.get('name') or 'Untitled'}  ·  {policy.get('status') or 'unknown'}"


def _summary(row: dict) -> dict:
    details = row.get("details") or {}
    latency = details.get("latency_ms") or {}
    total = latency.get("total")
    question = str(row.get("question") or "")
    return {
        "Time": str(row.get("verified_at") or "")[:19],
        "Verdict": components_verdict(row),
        "Request": question[:80],
        "Extractor": details.get("extractor") or "",
        "Total ms": f"{float(total):.0f}" if isinstance(total, (int, float)) else "",
    }


def components_verdict(row: dict) -> str:
    from streamlit_ui import components

    return components.verdict_of(row)


def _option(row: dict) -> str:
    question = str(row.get("question") or "")[:60]
    when = str(row.get("verified_at") or "")[:19]
    return f"{when}  {components_verdict(row)}  {question}"


if __name__ == "__main__":
    render()
