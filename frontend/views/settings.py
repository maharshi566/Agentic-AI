import streamlit as st

from backend import service
from frontend import session

st.title("Settings")

st.subheader("OpenAI connection")
source = session.key_source()
if source:
    st.info(
        f'An API key is available from {source}. Use "Test the connection" to check that it works.'
    )
else:
    st.warning("No API key is set. Enter one below to use the assistant.")
st.caption("A key entered here is kept only in this browser session and is never saved to disk.")

entered = st.text_input("OpenAI API key", type="password", placeholder="sk-...")
model = st.selectbox(
    "Model",
    session.MODEL_CHOICES,
    index=session.MODEL_CHOICES.index(session.selected_model())
    if session.selected_model() in session.MODEL_CHOICES
    else 0,
    help="gpt-4o-mini is cheaper and fast enough for most questions; gpt-4o is more capable.",
)

save_column, test_column = st.columns(2)
if save_column.button("Use this key and model", type="primary"):
    if entered:
        st.session_state[session.API_KEY] = entered
    st.session_state[session.MODEL] = model
    st.rerun()

if test_column.button("Test the connection"):
    try:
        service.verify_api_key(entered or st.session_state.get(session.API_KEY))
    except service.EXPECTED_ERRORS as exc:
        st.error(service.describe_error(exc, "Enter a valid key above."))
    else:
        st.success("Connected to OpenAI.")

st.divider()
st.subheader("Demo data")
status = service.data_status()
st.write(
    f"The assistant analyses a synthetic supermarket dataset as of **{status['as_of']}** "
    f"stored at `{status['path']}`."
)
with st.expander("Regenerate the demo data"):
    st.write("Replaces all sales, prices, promotions and stock levels with a new random dataset.")
    seed = st.number_input("Random seed", min_value=0, value=service.DEFAULT_DATA_SEED, step=1)
    confirmed = st.checkbox("I understand this replaces the current data")
    if st.button("Regenerate", disabled=not confirmed):
        try:
            service.regenerate_data(int(seed))
        except OSError as exc:
            st.error(f"Could not replace the database: {exc}")
        else:
            st.cache_data.clear()
            st.success(f"Demo data regenerated with seed {int(seed)}.")

with st.expander("Storage"):
    st.write(
        f"Database size: {status['size_mb']:.1f} MB. Free disk space: {status['free_gb']:.1f} GB."
    )
