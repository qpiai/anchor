"""Anchor policy verification UI."""

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from streamlit_ui.views.history import render as render_history
from streamlit_ui.views.policies import render as render_policies
from streamlit_ui.views.settings import render as render_settings
from streamlit_ui.views.verify import render as render_verify

CSS = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
.block-container {padding-top: 2.2rem; padding-bottom: 2.5rem; max-width: 980px;}
h1, h2, h3 {font-weight: 560; letter-spacing: -0.02em;}
.verdict {
  display: inline-block;
  padding: 0.45rem 1rem;
  border-radius: 999px;
  font-size: 1.05rem;
  font-weight: 650;
  letter-spacing: 0.05em;
}
.verdict-VALID {background: #e5f6ec; color: #0e7a3d;}
.verdict-INVALID {background: #fdecec; color: #b42318;}
.verdict-NEEDS_CLARIFICATION {background: #fff4e0; color: #b54708;}
.verdict-ERROR {background: #eef0f3; color: #5c6570;}
[data-testid="stDataFrame"] {border: 1px solid #e6e8ec; border-radius: 8px;}
</style>
"""

st.set_page_config(page_title="Anchor", layout="centered", initial_sidebar_state="expanded")
st.markdown(CSS, unsafe_allow_html=True)

nav = st.navigation(
    [
        st.Page(render_verify, title="Verify", url_path="verify", default=True),
        st.Page(render_policies, title="Policies", url_path="policies"),
        st.Page(render_history, title="History", url_path="history"),
        st.Page(render_settings, title="Settings", url_path="settings"),
    ]
)
nav.run()
