"""Upload, inspect, and compile policies."""

import json

DOMAINS = ["hr", "legal", "finance", "operations", "compliance"]


def render() -> None:
    import streamlit as st

    from streamlit_ui import api, cache
    from streamlit_ui.api import ApiError

    st.header("Policies")
    _upload()

    try:
        policies = cache.cached_policies(api.base_url())
    except ApiError as exc:
        st.error(str(exc))
        return

    if not policies:
        st.info("No policies yet.")
        return

    ordered = sorted(policies, key=lambda p: 0 if str(p.get("status")).lower() in ("compiled", "active") else 1)
    st.dataframe(_rows(ordered), hide_index=True, width="stretch")

    labels = ["Select a policy"] + [_label(p) for p in ordered]
    by_label = {_label(p): p for p in ordered}
    choice = st.selectbox("Open", labels, key="policy_open")
    if choice == "Select a policy":
        return

    summary = by_label[choice]
    policy_id = str(summary["id"])
    try:
        policy = api.get_policy(policy_id)
    except ApiError as exc:
        st.error(str(exc))
        return

    st.subheader(policy.get("name") or "Policy")
    st.caption(f"{policy.get('domain') or ''} · {policy.get('status') or ''} · v{policy.get('version') or ''}")
    _variables(policy)
    _rules(policy)
    _actions(policy)


def _upload() -> None:
    import streamlit as st

    from streamlit_ui import api, cache
    from streamlit_ui.api import ApiError

    with st.expander("Upload a document", expanded=False):
        uploaded = st.file_uploader("Document", type=["pdf", "docx", "txt"])
        domain = st.selectbox("Domain", DOMAINS, key="upload_domain")
        if st.button("Create policy", key="upload_btn"):
            if uploaded is None:
                st.error("Choose a file first.")
                return
            with st.spinner("Creating policy. This usually takes 10 to 30 seconds."):
                try:
                    doc = api.upload_document(uploaded.name, uploaded.getvalue(), domain)
                    created = api.wait_for_policy(str(doc["document_id"]))
                except ApiError as exc:
                    st.error(str(exc))
                    return
            cache.clear()
            st.success(f"Created {created.get('name') or 'policy'}.")
            st.rerun()


def _rows(policies: list) -> list[dict]:
    rows = []
    for policy in policies:
        rows.append(
            {
                "Name": policy.get("name") or "",
                "Domain": policy.get("domain") or "",
                "Status": policy.get("status") or "",
                "Variables": len(policy.get("variables") or []),
                "Rules": len(policy.get("rules") or []),
                "Updated": str(policy.get("updated_at") or "")[:19],
            }
        )
    return rows


def _label(policy: dict) -> str:
    return f"{policy.get('name') or 'Untitled'}  ·  {policy.get('status') or 'unknown'}"


def _variables(policy: dict) -> None:
    import streamlit as st

    from streamlit_ui import api, cache
    from streamlit_ui.api import ApiError

    variables = policy.get("variables") or []
    st.markdown("**Variables**")
    if not variables:
        st.caption("None defined.")
        return
    st.dataframe(
        [
            {
                "Name": var.get("name"),
                "Type": var.get("type"),
                "Mandatory": bool(var.get("is_mandatory", True)),
                "Default": var.get("default_value") or "",
                "Possible values": ", ".join(var.get("possible_values") or []),
            }
            for var in variables
            if isinstance(var, dict)
        ],
        hide_index=True,
        width="stretch",
    )
    names = [var.get("name") for var in variables if isinstance(var, dict) and var.get("name")]
    picked = st.selectbox("Edit variable", names, key=f"var_{policy['id']}")
    current = next(var for var in variables if var.get("name") == picked)
    mandatory = st.checkbox("Mandatory", value=bool(current.get("is_mandatory", True)), key=f"mand_{policy['id']}")
    default = st.text_input("Default (blank clears it)", value=current.get("default_value") or "", key=f"def_{policy['id']}")
    if st.button("Save variable", key=f"save_var_{policy['id']}"):
        try:
            api.patch_variable(
                str(policy["id"]),
                picked,
                is_mandatory=mandatory,
                default_value=default,
            )
        except ApiError as exc:
            st.error(str(exc))
            return
        cache.clear()
        st.success("Variable updated. Policy status is draft until you compile again.")
        st.rerun()


def _rules(policy: dict) -> None:
    import streamlit as st

    rules = policy.get("rules") or []
    st.markdown("**Rules**")
    if not rules:
        st.caption("None defined.")
        return
    st.dataframe(
        [
            {
                "Id": rule.get("id"),
                "Condition": rule.get("condition"),
                "Conclusion": rule.get("conclusion"),
                "Description": rule.get("description"),
            }
            for rule in rules
            if isinstance(rule, dict)
        ],
        hide_index=True,
        width="stretch",
    )


def _actions(policy: dict) -> None:
    import streamlit as st

    from streamlit_ui import api, cache
    from streamlit_ui.api import ApiError

    policy_id = str(policy["id"])
    col1, col2, col3 = st.columns(3)
    if col1.button("Compile", key=f"compile_{policy_id}"):
        with st.spinner("Compiling"):
            try:
                result = api.compile_policy(policy_id)
            except ApiError as exc:
                st.error(str(exc))
                result = None
        if result is not None:
            cache.clear()
            if str(result.get("status")).lower() == "success":
                st.success("Compiled.")
            else:
                st.error("Compilation failed: " + "; ".join(result.get("errors") or []))
            st.rerun()

    if col2.button("Variable analysis", key=f"analysis_{policy_id}"):
        try:
            st.session_state["analysis"] = api.variable_analysis(policy_id)
            st.session_state["analysis_for"] = policy_id
        except ApiError as exc:
            st.error(str(exc))

    if st.button("Check rules against source", key=f"ground_{policy_id}"):
        with st.spinner("Checking rules"):
            try:
                grounding = api.rule_grounding(policy_id)
            except ApiError as exc:
                st.error(str(exc))
                grounding = None
        if grounding is not None:
            flagged = [row for row in grounding.get("rules") or [] if row.get("flag")]
            if not flagged:
                st.success("No rules were flagged.")
            for row in flagged:
                st.warning(f"{row.get('rule_id')} ({row.get('supported_probability')})")
                st.caption(row.get("passage") or "")

    if col3.button("Fix missing variables", key=f"fix_{policy_id}"):
        try:
            fixed = api.fix_missing_variables(policy_id)
        except ApiError as exc:
            st.error(str(exc))
        else:
            cache.clear()
            st.success(fixed.get("message") or "Updated variables.")
            st.rerun()

    if st.session_state.get("analysis_for") == policy_id and st.session_state.get("analysis"):
        analysis = st.session_state["analysis"]
        missing = analysis.get("missing_variables") or []
        unused = analysis.get("unused_variables") or []
        st.caption(
            f"Defined {analysis.get('total_defined_variables', 0)}, "
            f"referenced {analysis.get('total_referenced_variables', 0)}."
        )
        st.write("Missing: " + (", ".join(missing) if missing else "none"))
        st.write("Unused: " + (", ".join(unused) if unused else "none"))

    if st.button("Generate and run test scenarios", key=f"tests_{policy_id}"):
        with st.spinner("Generating and running scenarios"):
            try:
                report = api.run_test_scenarios(policy_id)
            except ApiError as exc:
                st.error(str(exc))
                report = None
        if report is not None:
            rate = report.get("success_rate")
            passed = report.get("passed_scenarios", 0)
            total = report.get("total_scenarios", 0)
            shown = f"{float(rate):.0%}" if isinstance(rate, (int, float)) else "n/a"
            st.metric("Pass rate", shown)
            st.caption(f"{passed} passed of {total}")

    if st.button("Delete", key=f"delete_{policy_id}"):
        st.session_state["confirm_delete"] = policy_id
    if st.session_state.get("confirm_delete") == policy_id:
        st.warning(f"Delete {policy.get('name')}? This cannot be undone.")
        if st.button("Confirm delete", key=f"confirm_{policy_id}"):
            try:
                api.delete_policy(policy_id)
            except ApiError as exc:
                st.error(str(exc))
            else:
                cache.clear()
                st.session_state["confirm_delete"] = None
                st.success("Deleted.")
                st.rerun()

    with st.expander("Advanced: raw JSON"):
        editable = {
            "name": policy.get("name"),
            "description": policy.get("description"),
            "variables": policy.get("variables") or [],
            "rules": policy.get("rules") or [],
            "constraints": policy.get("constraints") or [],
            "examples": policy.get("examples") or [],
        }
        raw = st.text_area("Policy JSON", json.dumps(editable, indent=2), height=240, key=f"json_{policy_id}")
        if st.button("Save JSON", key=f"save_json_{policy_id}"):
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                st.error(f"Invalid JSON: {exc}")
                return
            try:
                api.update_policy(policy_id, payload)
            except ApiError as exc:
                st.error(str(exc))
                return
            cache.clear()
            st.success("Saved. Content changes return the policy to draft.")
            st.rerun()


if __name__ == "__main__":
    render()
