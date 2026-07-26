import os

import streamlit as st
import plotly.express as px
import pandas as pd
from agent import run_agent
from providers import PROVIDERS, get_provider

st.set_page_config(page_title="NASCAR Analytics", page_icon="🏁", layout="wide")
st.title("NASCAR Analytics Chatbot")

STARTER_QUESTIONS = [
    "Who has the most all-time Cup wins?",
    "Best road course drivers since 2015",
    "Compare Hendrick vs Joe Gibbs Racing wins by decade",
    "Which manufacturer dominates superspeedways?",
    "Show Kyle Larson's win rate by season",
]

if "display_messages" not in st.session_state:
    st.session_state.display_messages = []
if "api_messages" not in st.session_state:
    st.session_state.api_messages = []
if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = None


def render_chart(spec: dict):
    df = pd.DataFrame(spec["data"])
    if df.empty:
        return
    kwargs = {"x": spec["x"], "y": spec["y"], "title": spec["title"]}
    if spec.get("color") and spec["color"] in df.columns:
        kwargs["color"] = spec["color"]

    chart_type = spec["chart_type"]
    if chart_type == "bar":
        fig = px.bar(df, **kwargs)
    elif chart_type == "line":
        fig = px.line(df, **kwargs)
    elif chart_type == "scatter":
        fig = px.scatter(df, **kwargs)
    elif chart_type == "pie":
        fig = px.pie(df, names=spec["x"], values=spec["y"], title=spec["title"])
    else:
        fig = px.bar(df, **kwargs)

    fig.update_layout(height=450, xaxis_tickangle=-35, margin=dict(b=120))
    st.plotly_chart(fig, use_container_width=True)


with st.sidebar:
    st.header("Settings")

    provider_key = st.selectbox(
        "Provider",
        list(PROVIDERS),
        format_func=lambda k: PROVIDERS[k].label,
        help="Any backend that supports tool calling works — hosted or local.",
    )
    spec = PROVIDERS[provider_key]

    if spec.requires_key:
        api_key = st.text_input(
            f"{spec.label} API key",
            type="password",
            value=os.environ.get(spec.key_env, ""),
            help=f"Used for this session only, never stored. Get one at {spec.key_help}.",
        )
    else:
        api_key = ""
        st.caption(f"No key needed — {spec.key_help}")

    model = st.selectbox("Model", spec.models)
    custom_model = st.text_input(
        "Custom model ID",
        placeholder="optional — overrides the selection above",
        help="Model IDs change often. Paste any ID this provider serves.",
    )
    model = custom_model.strip() or model

    effort = "high"
    if provider_key == "anthropic":
        effort = st.select_slider(
            "Reasoning effort",
            options=["low", "medium", "high", "xhigh"],
            value="high",
            help="Higher effort means deeper reasoning and more tokens per answer.",
        )

    active_series = st.selectbox("Series", ["Cup", "Xfinity", "Truck"])

    st.markdown("---")
    st.markdown("**Try asking:**")
    for q in STARTER_QUESTIONS:
        if st.button(q, use_container_width=True):
            st.session_state.pending_prompt = q
            st.rerun()

    st.markdown("---")
    if st.button("Clear conversation", use_container_width=True):
        st.session_state.display_messages = []
        st.session_state.api_messages = []
        st.rerun()


for msg in st.session_state.display_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        for chart_spec in msg.get("charts", []):
            render_chart(chart_spec)


def handle_prompt(prompt: str):
    if spec.requires_key and not api_key:
        st.error(f"Enter your {spec.label} API key in the sidebar to start asking questions.")
        return

    st.session_state.display_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Remember where this turn started so a failure can be rolled back cleanly.
    turn_start = len(st.session_state.api_messages)
    st.session_state.api_messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        with st.status("Analyzing...", expanded=True) as status:
            try:
                def on_tool_call(label: str):
                    status.update(label=label)

                provider = get_provider(
                    provider_key, api_key=api_key, model=model, effort=effort
                )
                response_text, charts = run_agent(
                    st.session_state.api_messages,
                    provider=provider,
                    active_series=active_series,
                    on_tool_call=on_tool_call,
                )
                status.update(label="Done", state="complete", expanded=False)
            except Exception as e:
                # Drop the partial turn — a dangling tool_use with no tool_result
                # would make every later request fail.
                del st.session_state.api_messages[turn_start:]
                response_text = f"Error: {e}"
                charts = []
                status.update(label="Error", state="error", expanded=False)
                st.error(response_text)

        st.markdown(response_text)
        for chart_spec in charts:
            render_chart(chart_spec)

    st.session_state.display_messages.append(
        {"role": "assistant", "content": response_text, "charts": charts}
    )


# Handle sidebar button clicks
if st.session_state.pending_prompt:
    prompt = st.session_state.pending_prompt
    st.session_state.pending_prompt = None
    handle_prompt(prompt)

# Handle chat input
if prompt := st.chat_input(f"Ask about {active_series} Series..."):
    handle_prompt(prompt)
