import streamlit as st

from backend import service
from frontend.components import render_output
from frontend.forms import (
    CATEGORY,
    CATEGORY_ONLY_TOOLS,
    DAYS_TOOLS,
    DEFAULT_LOOKBACK_DAYS,
    MAX_DAYS,
    MIN_DAYS,
    PRODUCT,
    WHOLE_STORE,
    build_arguments,
)
from frontend.labels import TOOL_LABELS, TOOL_QUESTIONS

RESULT = "explore_result"

st.title("Explore analyses")
st.write(
    "Run any of the assistant's analyses yourself, without asking a question. "
    "This works without an OpenAI key."
)

catalog = service.product_catalog()
categories = sorted({item["category"] for item in catalog})
products = {item["sku"]: f"{item['sku']} · {item['name']}" for item in catalog}

tool = st.selectbox(
    "Analysis",
    service.analysis_names(),
    format_func=lambda name: f"{TOOL_LABELS[name]}: {TOOL_QUESTIONS[name]}",
)

if tool in CATEGORY_ONLY_TOOLS:
    scope = CATEGORY
    st.caption("This analysis always looks at one category.")
else:
    scope = st.radio("Scope", [WHOLE_STORE, CATEGORY, PRODUCT], horizontal=True)

category = st.selectbox("Category", categories, disabled=scope != CATEGORY)
product = st.selectbox(
    "Product", list(products), format_func=products.get, disabled=scope != PRODUCT
)
days = st.slider(
    "Look back (days)",
    MIN_DAYS,
    MAX_DAYS,
    DEFAULT_LOOKBACK_DAYS,
    disabled=tool not in DAYS_TOOLS,
)

if st.button("Run analysis", type="primary"):
    args = build_arguments(tool, scope, category, product, days)
    try:
        st.session_state[RESULT] = {
            "tool": tool,
            "args": args,
            "output": service.run_analysis(tool, args),
        }
    except service.ToolInputError as exc:
        st.session_state[RESULT] = {"tool": tool, "args": args, "error": str(exc)}

if result := st.session_state.get(RESULT):
    st.divider()
    st.subheader(TOOL_LABELS[result["tool"]])
    if "error" in result:
        st.warning(result["error"])
    else:
        render_output(result["tool"], result["output"])
        with st.expander("Technical details"):
            st.json(
                {
                    "analysis": result["tool"],
                    "arguments": result["args"],
                    "output": result["output"],
                }
            )
