import streamlit as st
import pandas as pd

from ui.components import sidebar_section, recipe_card, takeout_controls
from ui.layout import page_header
from services.google_sheets_loader import load_workbook
from services.llm_client import generate_takeout_recommendations



def render_takeout_page():
    page_header("Takeout Recommender", "Get personalized takeout suggestions")

    (
        meals_df,
        ingredients_df,
        recipes_df,
        store_layout_df,
        history_df,
        weekly_plan_df,
        grocery_list_df
    ) = load_workbook()

    params = takeout_controls(meals_df)

    # ---------------------------------------------------------
    # Debug panel (main page)
    # ---------------------------------------------------------
    if st.checkbox("Show Debug Data"):
        st.subheader("Params JSON")
        st.code(params)

        st.subheader("Takeout Meals JSON")
        takeout_df = meals_df[meals_df["Category"] == "Takeout"]
        st.code(takeout_df.to_dict(orient="records"))

        st.subheader("Full Meals JSON (optional)")
        st.code(meals_df.to_dict(orient="records"))

        st.subheader("Notes")
        st.code(params.get("notes", ""))

    if not params["generate"]:
        st.info("Use the controls in the sidebar and click **Recommend Takeout**.")
        return

    api_key = st.session_state.get("openai_api_key")
    if not api_key:
        st.error("Enter your OpenAI API key in the sidebar to get recommendations.")
        return

    takeout_df = meals_df[meals_df["Category"] == "Takeout"]
    meals_df_json = takeout_df.to_json(orient="records")

    recommendations = generate_takeout_recommendations(params, meals_df_json, api_key=api_key)


    st.markdown("### Recommended Takeout Options")

    for rec in recommendations:
        recipe_card(
            rec["Name"],
            {
                "Cuisine": rec["Cuisine"],
                "Status": rec["Type"],
                "Attributes": ", ".join(rec["Attributes"]),
                "Distance": rec["Distance"],
                "Reasoning": rec["Reasoning"]
            }
        )
        st.markdown("")


    # --- Adjustment Box (LLM-ready) ---
    st.markdown("---")
    st.markdown("### Adjust Recommendations")

    adjust_text = st.text_area(
        "Describe what you'd like to change",
        placeholder="e.g., show cheaper options, avoid fried food, something spicier, more kid-friendly..."
    )

    apply_changes = st.button("Apply Changes")

    if apply_changes:

        if not api_key:
            st.error("Enter your OpenAI API key in the sidebar to apply changes.")
            return

        updated_recommendations = generate_takeout_recommendations(
            params,
            meals_df_json,
            api_key=api_key,
            feedback=adjust_text
        )

        st.markdown("### Updated Recommendations")

        for rec in updated_recommendations:
            recipe_card(
                rec["Name"],
                {
                    "Cuisine": rec["Cuisine"],
                    "Status": rec["Type"],
                    "Attributes": ", ".join(rec["Attributes"]),
                    "Distance": rec["Distance"],
                    "Reasoning": rec["Reasoning"]
                }
            )
            st.markdown("")

