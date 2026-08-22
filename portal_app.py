"""FarmHerd project portal for the unified public host."""

import streamlit as st


st.set_page_config(page_title="FarmHerd AI", page_icon="F", layout="wide")

st.title("FarmHerd AI")
st.subheader("Smarter alerts. Healthier herds. Stronger farmers.")
st.write(
    "A unified home for livestock health, weather intelligence, and farmer tools. "
    "Choose a service below to get started."
)

tab_assistant, tab_tools, tab_about = st.tabs(["Assistant", "Livestock Tools", "About Us"])

with tab_assistant:
    st.markdown("### Farmer Assistant")
    st.write("The authenticated farmer assistant is the next service to be connected to this unified portal.")
    st.info("Assistant integration point reserved at /assistant/")

with tab_tools:
    left, right = st.columns(2)
    with left:
        st.markdown("### Weather and Heat Alerts")
        st.write("View PIN-specific forecasts, THI heat-stress warnings, and livestock safety guidance.")
        st.link_button("Open Weather Advisory", "/weather/")
    with right:
        st.markdown("### Voice Onboarding")
        st.write("Capture farmer and farm details through conversational onboarding.")
        st.link_button("Open Onboarding", "/onboarding/")

with tab_about:
    st.markdown("### About FarmHerd AI")
    st.write(
        "FarmHerd AI combines weather, livestock health records, feed-market information, "
        "and conversational AI to help farmers act before problems become emergencies."
    )
    st.markdown("### Project Links")
    st.link_button("GitHub Repository", "https://github.com/himanshuchoudhary247/farm_logging")
    st.link_button("Project Documentation", "https://github.com/himanshuchoudhary247/farm_logging/tree/main/docs")

st.caption("FarmHerd AI | Livestock-first digital advisory platform")
