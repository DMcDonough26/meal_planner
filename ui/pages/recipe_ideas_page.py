import streamlit as st

from services.google_sheets_loader import load_workbook
from services.llm_client import generate_recipe_ideas
from ui.components import recipe_ideas_controls, recipe_idea_card


def render_recipe_ideas_page():
    st.title("Recipe Ideas")
    st.caption(
        "Get brand-new recipe suggestions based on your cookbook's taste "
        "patterns. These are ideas only -- they're never added to your "
        "meal plan or grocery list automatically."
    )

    (
        meals_df,
        ingredients_df,
        recipes_df,
        store_layout_df,
        history_df,
        weekly_plan_df,
        grocery_list_df
    ) = load_workbook()

    # Recipe ideas only ever look at Existing (cookbook) or New (idea-only) --
    # this page IS the "new" side of that fork, so it just uses the cookbook
    # for taste-pattern context, excluding Takeout/Staples (not real recipes).
    cookbook_df = meals_df[~meals_df["Category"].isin(["Takeout", "Staples"])]
    cookbook_json = cookbook_df.to_dict(orient="records")

    params = recipe_ideas_controls(meals_df)

    if params["generate"]:
        st.session_state.recipe_ideas_regen_counter = (
            st.session_state.get("recipe_ideas_regen_counter", 0) + 1
        )
        st.session_state.recipe_ideas_generate = True

    if "recipe_ideas" not in st.session_state and not st.session_state.get("recipe_ideas_generate"):
        st.info("Use the controls in the sidebar and click **Suggest Recipe Ideas** to get started.")
        return

    if st.session_state.get("recipe_ideas_generate"):
        api_key = st.session_state.get("openai_api_key")
        if not api_key:
            st.error("Enter your OpenAI API key in the sidebar to get recipe ideas.")
            st.session_state.recipe_ideas_generate = False
            return

        try:
            ideas = generate_recipe_ideas(
                params,
                cookbook_json,
                api_key=api_key,
                cache_bust=st.session_state.recipe_ideas_regen_counter,
            )
        except Exception as e:
            st.error(f"Couldn't get recipe ideas: {e}")
            st.session_state.recipe_ideas_generate = False
            return

        st.session_state.recipe_ideas = ideas
        st.session_state.recipe_ideas_generate = False

    ideas = st.session_state.recipe_ideas

    for idea in ideas:
        recipe_idea_card(
            idea["Name"],
            idea.get("Source", "Unknown"),
            idea.get("Link"),
            idea["Blurb"]
        )
        st.markdown("")

    # ---------------------------------------------------------
    # Footer -- refine with feedback, same pattern as Plan/Takeout
    # ---------------------------------------------------------
    st.markdown("---")
    st.markdown("### Refine These Ideas")
    feedback = st.text_area("What would you change?", key="recipe_ideas_feedback")

    if st.button("Get New Ideas"):
        api_key = st.session_state.get("openai_api_key")
        if not feedback.strip():
            st.warning("Enter what you'd like to change above before applying.")
        elif not api_key:
            st.error("Enter your OpenAI API key in the sidebar to apply changes.")
        else:
            st.session_state.recipe_ideas_regen_counter = (
                st.session_state.get("recipe_ideas_regen_counter", 0) + 1
            )

            try:
                new_ideas = generate_recipe_ideas(
                    params,
                    cookbook_json,
                    api_key=api_key,
                    feedback=feedback,
                    cache_bust=st.session_state.recipe_ideas_regen_counter,
                )
            except Exception as e:
                st.error(f"Couldn't apply changes: {e}")
                new_ideas = None

            if new_ideas is not None:
                st.session_state.recipe_ideas = new_ideas
                st.success("Updated with new ideas.")
                st.rerun()
