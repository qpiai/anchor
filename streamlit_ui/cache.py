"""Short-lived caches for list endpoints. Cleared after mutations."""

import streamlit as st

from streamlit_ui import api


@st.cache_data(ttl=10)
def cached_policies(base: str) -> list:
    return api.list_policies()


@st.cache_data(ttl=10)
def cached_verifications(base: str, policy_id: str) -> list:
    return api.list_verifications(policy_id)


def clear() -> None:
    st.cache_data.clear()
