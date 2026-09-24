import streamlit as st

st.set_page_config(page_title="Merchandising Assistant", layout="wide")

navigation = st.navigation(
    [
        st.Page("views/ask.py", title="Ask the assistant", icon=":material/chat:", default=True),
        st.Page("views/overview.py", title="Business overview", icon=":material/dashboard:"),
        st.Page("views/explore.py", title="Explore analyses", icon=":material/query_stats:"),
        st.Page("views/settings.py", title="Settings", icon=":material/settings:"),
    ]
)
navigation.run()
