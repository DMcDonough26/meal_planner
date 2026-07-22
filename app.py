import streamlit as st
from ui.pages.plan_page import render_plan_page
from ui.pages.takeout_page import render_takeout_page


st.set_page_config(
    page_title="Meal Planner",
    page_icon="🥘",
    layout="wide",
)

def main():
    st.sidebar.title("Meal Planner")
    page = st.sidebar.selectbox(
        "Page",
        ["Plan", "Takeout"]
    )


    if page == "Plan":
        render_plan_page()

    elif page == "Takeout":
        render_takeout_page()


if __name__ == "__main__":
    main()
