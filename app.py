
"""Streamlit app for Axon Health analytics."""

import streamlit as st

from src.agent import generate_spec
from src.database import run_query
from src.charts import render_chart


st.set_page_config(
    page_title="Axon Health | Harbourview Analytics",
    page_icon="📊",
    layout="wide",
)

st.title("Axon Health | Harbourview Analytics")
st.caption("Ask questions about admissions, occupancy, conversion, and length of stay.")

# Fixed synthetic tenant for the take-home prototype.
TENANT_ID = "harbourview"

# Initialize chat history.
if "messages" not in st.session_state:
    st.session_state.messages = []

if "pending_question" not in st.session_state:
    st.session_state.pending_question = None


# Display previous messages.
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

        if "spec" in message:
            with st.expander("View JSON specification"):
                st.json(message["spec"])

            render_chart(
                message["dashboard_spec"],
                message["data"],
            )


# Always display the chat input.
question = st.chat_input("Ask an analytics question...")

if question:

    # Display and save user message.
    st.session_state.messages.append({
        "role": "user",
        "content": question,
    })

    with st.chat_message("user"):
        st.write(question)

    # Include previous question if clarifying.
    if st.session_state.pending_question:
        full_question = (
            f"Original question: {st.session_state.pending_question}\n"
            f"User clarification: {question}"
        )
    else:
        full_question = question

    with st.chat_message("assistant"):
        with st.spinner("Analyzing your question..."):

            try:
                result = generate_spec(full_question)

                if result.action == "clarify":
                    st.write(result.message)

                    st.session_state.pending_question = full_question

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": result.message,
                    })

                elif result.action == "unsupported":
                    st.warning(result.message)

                    st.session_state.pending_question = None

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": result.message,
                    })

                elif result.action == "query":
                    st.session_state.pending_question = None

                    spec = result.spec

                    # Execute a validated, read-only MongoDB aggregation.
                    df = run_query(
                        spec,
                        tenant_id=TENANT_ID,
                    )

                    st.write("Here are the results:")

                    render_chart(spec, df)

                    with st.expander("View JSON specification"):
                        st.json(spec.model_dump(mode="json"))

                    with st.expander("View query results"):
                        st.dataframe(df)

                    # Save results to session state.
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": "Here are the results:",
                        "spec": spec.model_dump(mode="json"),
                        "dashboard_spec": spec,
                        "data": df,
                    })

            except Exception as e:
                st.error(f"Error: {e}")
