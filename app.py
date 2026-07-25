import streamlit as st
from ui.pages.plan_page import render_plan_page
from ui.pages.takeout_page import render_takeout_page
from ui.pages.recipe_ideas_page import render_recipe_ideas_page

from ui.components import openai_api_key_input

st.set_page_config(
    page_title="Meal Planner",
    page_icon="🥘",
    layout="wide",
)

def main():
    st.sidebar.title("Meal Planner")
    page = st.sidebar.selectbox(
        "Page",
        ["Plan", "Takeout", "Recipe Ideas"]
    )

    with st.sidebar.expander("Owner Access"):
        passcode = st.text_input("Owner passcode", type="password", key="owner_passcode_input")
        if passcode:
            if passcode == st.secrets.get("OWNER_PASSCODE"):
                st.session_state["owner_unlocked"] = True
            elif not st.session_state.get("owner_unlocked"):
                st.error("Incorrect passcode.")
        if st.session_state.get("owner_unlocked"):
            st.success("Owner mode unlocked for this session.")

    st.session_state["openai_api_key"] = openai_api_key_input()

    if page == "Plan":
        render_plan_page()

    elif page == "Takeout":
        render_takeout_page()

    elif page == "Recipe Ideas":
        render_recipe_ideas_page()


if __name__ == "__main__":
    main()
