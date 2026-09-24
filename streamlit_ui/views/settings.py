"""Session API target and a short health summary."""


def render() -> None:
    import streamlit as st

    from streamlit_ui import api
    from streamlit_ui.api import ApiError

    st.header("Settings")
    if "api_base_url" not in st.session_state:
        st.session_state.api_base_url = api.env_base_url()
    st.text_input("API base URL", key="api_base_url")
    st.caption("Used for this session only. Leave it as the running Anchor server.")

    url = api.base_url()
    st.write(f"In use: `{url}`")

    try:
        health = api.health()
    except ApiError as exc:
        st.error(str(exc))
        return

    components = health.get("components") or {}
    database = str(components.get("database") or "unknown")
    st.write(f"Health: {health.get('status') or 'unknown'}")
    st.write(f"Database: {database}")

    try:
        status = api.status()
    except ApiError as exc:
        st.error(str(exc))
        status = {}

    try:
        config = api.config()
    except ApiError as exc:
        st.error(str(exc))
        config = {}

    extractor = _pick(status, config, "extractor_mode", "extractor")
    model = _pick(status, config, "model", "default_llm_provider")
    jev = _flag(status, config)
    st.write(f"Extractor: {extractor}")
    st.write(f"Model: {model}")
    st.write(f"Jev configured: {jev}")


def _pick(status: dict, config: dict, *keys: str) -> str:
    for source in (status, config, status.get("statistics") or {}, config):
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = source.get(key)
            if value not in (None, ""):
                return str(value)
    return "not reported"


def _flag(status: dict, config: dict) -> str:
    for source in (status, config):
        if not isinstance(source, dict):
            continue
        for key in ("jev_configured", "jev"):
            if key in source:
                return "yes" if source[key] else "no"
    return "not reported"


if __name__ == "__main__":
    render()
