import streamlit as st

from services.google_sheets_loader import load_workbook
from services.llm_client import generate_recipe_ideas
from services.google_sheets_writer import write_recipe_idea_to_cookbook
from config.constants import is_owner_mode
from ui.layout import page_header
from ui.components import recipe_ideas_controls, render_metadata_card, compute_card_height


def render_recipe_ideas_page():
    page_header(
        "Recipe Ideas",
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
        # Remember what was actually asked for at generation time, since the
        # sidebar's num_ideas widget can change on a later rerun before the
        # user regenerates -- comparing against a stale/live params value
        # would misreport the shortfall.
        st.session_state.recipe_ideas_requested = params["num_ideas"]

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
            with st.spinner("Hunting down recipe ideas..."):
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
        st.session_state.recipe_ideas_added = set()
        st.session_state.recipe_ideas_generate = False

    ideas = st.session_state.recipe_ideas

    # ---------------------------------------------------------
    # Shortfall notice -- the model returns fewer ideas rather than
    # fabricate a chef/recipe/link, so a short list is a feature of the
    # no-fabrication guarantee, not a bug. Surface it as such.
    # ---------------------------------------------------------
    requested = st.session_state.get("recipe_ideas_requested", len(ideas))
    returned = len(ideas)

    if returned < requested:
        st.info(
            f"Found {returned} of {requested} ideas that matched your filters. "
            "Rather than invent a chef, recipe, or link to hit the number, "
            "the model only returns ideas it's confident are real. Loosen "
            "the cuisine, ingredient, or notes filters in the sidebar, or "
            "just hit **Get New Ideas** below for a fresh pass."
        )

    if "recipe_ideas_added" not in st.session_state:
        st.session_state.recipe_ideas_added = set()

    sizing = compute_card_height(
        ideas,
        title_fn=lambda idea: idea["Name"],
        body_fn=lambda idea: idea["Blurb"],
        extra_lines_fn=lambda idea: 3,  # link line + one badge line + a little breathing room
    )

    NUM_COLUMNS = 3
    columns = st.columns(NUM_COLUMNS)
    for i, idea in enumerate(ideas):
        with columns[i % NUM_COLUMNS]:
            link = idea.get("Link")
            render_metadata_card(
                idea["Name"],
                rank=i + 1,
                height=sizing.height,
                title_lines=sizing.title_lines,
                badges=[("🧑‍🍳 Chef", idea.get("Source", "Unknown"))],
                badges_position="top",
                top_link=f"[View recipe]({link})" if link else None,
                body=idea["Blurb"],
            )

            if is_owner_mode():
                if i in st.session_state.recipe_ideas_added:
                    st.caption("Added to your cookbook.")
                else:
                    if st.button("Add to my cookbook", key=f"recipe_idea_add_{i}"):
                        try:
                            new_id = write_recipe_idea_to_cookbook(idea, "Bulk", meals_df)
                        except Exception as e:
                            st.error(f"Couldn't add to cookbook: {e}")
                        else:
                            st.session_state.recipe_ideas_added.add(i)
                            st.success(
                                f"Added as {new_id} -- ranking fields (Cost, "
                                "Effort, etc.) are set to TBD until you fill "
                                "them in."
                            )
                            st.rerun()

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
                with st.spinner("Cooking up new ideas..."):
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
                st.session_state.recipe_ideas_added = set()
                st.session_state.recipe_ideas_requested = params["num_ideas"]
                st.success("Updated with new ideas.")
                st.rerun()
