from typing import Any

import streamlit as st

from backend import service
from frontend import session
from frontend.components import render_output
from frontend.forms import EXAMPLE, EXAMPLES, QUESTION, use_example
from frontend.labels import TOOL_LABELS, describe_arguments

ANSWER = "answer"


def run_question(question: str) -> None:
    with st.status("Planning the analysis and gathering evidence...", expanded=True) as status:
        try:
            state = session.ask(question)
        except service.EXPECTED_ERRORS as exc:
            st.session_state[ANSWER] = {
                "question": question,
                "error": service.describe_error(exc, session.KEY_HINT),
            }
            status.update(label="The assistant could not complete the analysis", state="error")
        else:
            st.session_state[ANSWER] = {"question": question, "state": state}
            status.update(label="Analysis complete", state="complete", expanded=False)


def show_plan(plan: Any) -> None:
    st.subheader("What the assistant set out to do")
    st.write(plan.objective)
    for number, step in enumerate(plan.steps, start=1):
        label = TOOL_LABELS[step.tool]
        scope = describe_arguments(step.args.model_dump())
        st.markdown(f"{number}. **{label}** ({scope}): {step.rationale}")


def show_evidence(results: dict[str, Any]) -> None:
    st.subheader("Evidence gathered")
    for item in sorted(results.values(), key=lambda r: r["index"]):
        title = f"{item['index'] + 1}. {TOOL_LABELS[item['tool']]} · "
        title += describe_arguments(item["args"])
        with st.expander(title, expanded=item["index"] == 0 or bool(item["error"])):
            if item["error"]:
                st.warning(item["error"])
            else:
                render_output(item["tool"], item["output"])


def show_answer(answer: dict[str, Any]) -> None:
    if "error" in answer:
        st.error(answer["error"])
        return

    state = answer["state"]
    if not state["plan"].steps:
        st.info(
            "This does not look like a merchandising question, so no analysis was run. "
            "Try one of the examples above."
        )
        return

    show_plan(state["plan"])
    show_evidence(state.get("tool_results", {}))
    with st.expander("Technical details"):
        st.json(
            {
                "plan": state["plan"].model_dump(),
                "tool_results": state.get("tool_results", {}),
            }
        )


st.title("Ask the assistant")
st.write(
    "Ask a merchandising question in plain English. The assistant plans the analysis, "
    "gathers evidence from sales, stock, pricing and market data, and shows what it found."
)

st.pills(
    "Try an example",
    EXAMPLES,
    key=EXAMPLE,
    on_change=use_example,
    label_visibility="collapsed",
)
question = st.text_area(
    "Your question",
    key=QUESTION,
    height=100,
    placeholder="For example: Which Snacks are slow movers we could drop?",
)

can_ask = session.api_key_available()
if not can_ask:
    st.info(
        "Add your OpenAI API key on the Settings page to ask questions. "
        "You can already explore the data from the other pages."
    )

if st.button("Ask", type="primary", disabled=not can_ask or not question.strip()):
    run_question(question.strip())

if answer := st.session_state.get(ANSWER):
    st.divider()
    st.markdown(f"**Question:** {answer['question']}")
    show_answer(answer)
