import streamlit as st
import pandas as pd

from ui.components import (
    sidebar_section,
    render_metadata_card,
    render_card_grid,
    takeout_controls,
    compute_card_height,
)
from ui.layout import page_header
from services.google_sheets_loader import load_workbook
from services.llm_client import generate_takeout_recommendations


def _render_takeout_cards(recommendations):
    """Renders a batch of takeout cards at a shared height so they line
    up regardless of how long each restaurant's name or reasoning note
    runs -- height is recomputed per batch (initial vs. adjusted
    recommendations are two different batches)."""
    sizing = compute_card_height(
        recommendations,
        title_fn=lambda rec: rec["Name"],
        body_fn=lambda rec: rec["Reasoning"],
        extra_lines_fn=lambda rec: 7,  # the 7-line attribute list below
    )

    def _render_takeout_card(rec, rank):
        render_metadata_card(
            rec["Name"],
            rank=rank,
            height=sizing.height,
            title_lines=sizing.title_lines,
            badges=[
                ("🌍 Cuisine", rec["Cuisine"]),
                ("⏱️ Pickup", rec["Pickup Time"]),
                ("🥗 Health", rec["Healthy"]),
                ("😋 Taste", rec["Taste"]),
                ("💰 Cost/Serving", rec["Cost per Serving"]),
                ("🚗 Drive-Thru", rec["Drive-Thru"]),
                ("🚚 Delivery", rec["Delivery"]),
            ],
            body=rec["Reasoning"],
        )

    render_card_grid(recommendations, _render_takeout_card)


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

    recommend_tab, browse_tab = st.tabs(["🍽️ Recommend Takeout", "📘 Browse Takeout"])

    with recommend_tab:
        _render_recommend_tab(params, meals_df)

    with browse_tab:
        _render_browse_takeout_tab(meals_df)


def _render_recommend_tab(params, meals_df):
    if not params["generate"]:
        st.info("Use the controls in the sidebar and click **Recommend Takeout**.")
        return

    api_key = st.session_state.get("openai_api_key")
    if not api_key:
        st.error("Enter your OpenAI API key in the sidebar to get recommendations.")
        return

    takeout_df = meals_df[meals_df["Category"] == "Takeout"]
    meals_df_json = takeout_df.to_json(orient="records")

    try:
        with st.spinner("Scouting nearby takeout options..."):
            recommendations = generate_takeout_recommendations(params, meals_df_json, api_key=api_key)
    except Exception as e:
        st.error(f"Couldn't get recommendations: {e}")
        st.session_state.generate_plan = False
        return

    if not recommendations:
        st.info(
            "No takeout options matched what you're looking for. Try "
            "loosening a cuisine or attribute filter in the sidebar, or "
            "broadening your notes, then click **Recommend Takeout** again."
        )
        return

    st.markdown("### Recommended Takeout Options")

    _render_takeout_cards(recommendations)


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

        try:
            with st.spinner("Adjusting your takeout picks..."):
                updated_recommendations = generate_takeout_recommendations(
                    params,
                    meals_df_json,
                    api_key=api_key,
                    feedback=adjust_text
                )
        except Exception as e:
            st.error(f"Couldn't get recommendations: {e}")
            st.session_state.generate_plan = False
            return

        if not updated_recommendations:
            st.info(
                "No options matched that adjustment. Try a less specific "
                "request, or loosen a filter in the sidebar."
            )
            return

        st.markdown("### Updated Recommendations")

        _render_takeout_cards(updated_recommendations)



def _render_browse_takeout_tab(meals_df):
    """Browsable view over every Takeout entry in the Meals sheet --
    independent of any generated recommendation. Search/filter/sort
    only; no LLM involved. No ingredient search here -- takeout
    entries aren't ingredient-modeled the way home-cooked meals are."""
    st.caption("Every takeout option in your database, searchable and browsable.")

    base_df = meals_df[meals_df["Category"] == "Takeout"]

    names = sorted(n for n in base_df["Meal Name"].unique() if n)
    name_search = st.selectbox("Search by name", ["Any"] + names)

    filter_cols = st.columns(3)
    with filter_cols[0]:
        cuisines = sorted(c for c in base_df["Cuisine"].unique() if c)
        cuisine_filter = st.multiselect("Cuisine", cuisines)
    with filter_cols[1]:
        # Delivery/Drive Thru are numeric columns in the sheet (see
        # the loader's _convert_numeric list) -- treating > 0 as
        # "available". If those are actually a 1-5 score rather than
        # a flag, swap this for a min-value filter instead.
        feature_filter = st.multiselect("Features", ["Delivery", "Drive-Thru"])
    with filter_cols[2]:
        sort_by = st.selectbox(
            "Sort by",
            [
                "Name",
                "Cost per Serving (low to high)",
                "Taste (high to low)",
                "Healthy (high to low)",
            ],
        )

    df = base_df.copy()
    if name_search != "Any":
        df = df[df["Meal Name"] == name_search]
    if cuisine_filter:
        df = df[df["Cuisine"].isin(cuisine_filter)]
    if "Delivery" in feature_filter:
        df = df[df["Delivery"] > 0]
    if "Drive-Thru" in feature_filter:
        df = df[df["Drive Thru"] > 0]

    if sort_by == "Cost per Serving (low to high)":
        df = df.sort_values("Cost per Serving", ascending=True, na_position="last")
    elif sort_by == "Taste (high to low)":
        df = df.sort_values("Taste", ascending=False, na_position="last")
    elif sort_by == "Healthy (high to low)":
        df = df.sort_values("Healthy", ascending=False, na_position="last")
    else:
        df = df.sort_values("Meal Name")

    st.caption(f"{len(df)} takeout option{'s' if len(df) != 1 else ''}")
    if df.empty:
        st.info("No takeout options match those filters.")
        return

    def _format_score(value):
        return "N/A" if pd.isna(value) else f"{value:g}"

    def _render_browse_takeout_card(rec, _rank):
        cost_value = rec["Cost per Serving"]
        formatted_cost = "N/A" if pd.isna(cost_value) else f"${float(cost_value):.2f}"

        badges = [b for b in [
            ("🌍 Cuisine", rec["Cuisine"]) if rec["Cuisine"] else None,
            ("💰 Cost/Serving", formatted_cost),
            ("🥗 Healthy", _format_score(rec["Healthy"])),
            ("😋 Taste", _format_score(rec["Taste"])),
            ("🚗 Drive-Thru", _format_score(rec["Drive Thru"])),
            ("🚚 Delivery", _format_score(rec["Delivery"])),
        ] if b]

        render_metadata_card(rec["Meal Name"], badges=badges)

    render_card_grid(df.to_dict(orient="records"), _render_browse_takeout_card)
