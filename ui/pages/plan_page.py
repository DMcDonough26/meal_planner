import streamlit as st
import pandas as pd
from ui.layout import page_header
from ui.components import (
    planning_controls,
    table_section,
    render_metadata_card,
    render_card_grid,
    render_day_plan_card,
    compute_card_height,
    compute_day_card_height,
)
from services.llm_client import generate_plan

from services.meal_filters import (
    filter_meals_for_planner,
    filter_meal_names_for_recipe_cards,
)

from services.google_sheets_loader import load_workbook
from services.google_sheets_writer import write_plan_to_google_sheets

from config.constants import is_owner_mode


def build_scaled_df(selected_df, recipes_df, params):
    # Merge selected meals (with scale factor) onto the base recipe/ingredient rows
    merged = recipes_df.merge(
        selected_df[["Meal Name", "Scale Factor"]],
        on="Meal Name",
        how="inner",
    )

    # Scaled Display Quantity = Display Quantity × Portion Used × Scale Factor
    merged["Scaled Display Quantity"] = (
        merged["Display Quantity"] * merged["Portion Used"] * merged["Scale Factor"]
    )

    # Add Store from params
    merged["Store"] = params["store_name"]

    # Keep columns in the canonical order you defined
    cols = [
        "Meal ID",
        "Meal Name",
        "Ingredient ID",
        "Ingredient Name",
        "Price Type",
        "Unit",
        "Quantity",
        "Price",
        "Portion Used",
        "Cost Used",
        "Display Quantity",
        "Display Unit",
        "Section",
        "Scale Factor",
        "Store",
        "Scaled Display Quantity",
    ]

    return merged[cols]


def build_grocery_df(scaled_df, params, store_layout_df):
    # Group by ingredient + section + unit + store + ingredient ID
    grouped = (
        scaled_df.groupby(
            ["Ingredient ID", "Ingredient Name", "Section", "Display Unit", "Store"],
            as_index=False
        )
        .agg({
            "Scaled Display Quantity": "sum",
            "Meal Name": lambda x: ", ".join(sorted(set(x)))
        })
    )

    # Rename aggregated meal names column
    grouped = grouped.rename(columns={"Meal Name": "Meal Names"})

    # ---------------------------------------------------------
    # Bring in aisle order from Store Layout (one row per Store + Section)
    # ---------------------------------------------------------
    store_sections = store_layout_df[
        store_layout_df["Store"] == params["store_name"]
    ][["Section", "Order Number"]]

    grouped = grouped.merge(store_sections, on="Section", how="left")

    # Sections with no match in Store Layout (typo, or a new Section not yet
    # mapped for this store) sort to the end rather than silently reordering
    # or raising, so they're still visible on the list -- just ungrouped by aisle.
    grouped = grouped.sort_values(
        by=["Order Number", "Section", "Ingredient Name"],
        na_position="last"
    ).reset_index(drop=True)

    return grouped


def render_plan_page():
    page_header("Weekly Meal Planner", "Local UI mockup using real workbook data")

    # ---------------------------------------------------------
    # Load workbook
    # ---------------------------------------------------------
    (
        meals_df,
        _ingredients_df,
        recipes_df,
        store_layout_df,
        history_df,
        _weekly_plan_df,
        _grocery_list_df
    ) = load_workbook()


    # ---------------------------------------------------------
    # Sidebar controls
    # ---------------------------------------------------------
    params = planning_controls(meals_df, store_layout_df)

    # ---------------------------------------------------------
    # Debug panel (main page)
    # ---------------------------------------------------------
    # if st.checkbox("Show Debug Data"):
    #     st.subheader("Params JSON")
    #     st.code(params)

    #     st.subheader("Meals JSON")
    #     st.code(meals_df.to_dict(orient="records"))

    #     st.subheader("Recipes JSON")
    #     st.code(recipes_df.to_dict(orient="records"))

    #     st.subheader("History JSON")
    #     st.code(history_df.to_dict(orient="records"))

    # ---------------------------------------------------------
    # Top-level tabs: LLM planning vs. the plain browsable database
    # (same split as the Cocktail Planner's "Plan a Drink" / "My Bar")
    # -- pulled out here, above the generate-plan gate below, so
    # Browse Meals works even before anyone's clicked Generate Plan.
    # ---------------------------------------------------------
    plan_tab, browse_tab = st.tabs(["📅 Plan a Week", "📘 Browse Meals"])

    with plan_tab:
        _render_plan_tab(params, meals_df, recipes_df, store_layout_df, history_df)

    with browse_tab:
        _render_browse_meals_tab(meals_df, recipes_df)


def _render_plan_tab(params, meals_df, recipes_df, store_layout_df, history_df):
    # ---------------------------------------------------------
    # If user has not clicked Generate Plan yet
    # ---------------------------------------------------------
    if "plan_data" not in st.session_state and not st.session_state.get("generate_plan"):
        st.info("Use the controls in the sidebar and click **Generate Plan** to generate your weekly plan.")
        return

    # ---------------------------------------------------------
    # Generate plan only when flag is set
    # ---------------------------------------------------------
    if st.session_state.generate_plan:
        api_key = st.session_state.get("openai_api_key")
        if not api_key:
            st.error("Enter your OpenAI API key in the sidebar to generate a plan.")
            st.session_state.generate_plan = False
            return

        planner_meals_df = filter_meals_for_planner(meals_df)
        workbook_json = {
            "meals": planner_meals_df.to_dict(orient="records"),  # was meals_df
            "recipes": recipes_df.to_dict(orient="records"),
            "history": history_df.to_dict(orient="records")
        }

        try:
            with st.spinner("Building your weekly plan..."):
                selected_df, plan_df = generate_plan(
                    params, workbook_json, api_key=api_key,
                    cache_bust=st.session_state.get("plan_regen_counter", 0),
                )
        except Exception as e:
            st.error(f"Couldn't generate a plan: {e}")
            st.session_state.generate_plan = False
            return

        # ---------------------------------------------------------
        # Always include the Staples meal
        # ---------------------------------------------------------
        staples_row = meals_df[meals_df["Meal Name"] == "Staples"].copy()

        if not staples_row.empty:
            staples_row["Scale Factor"] = 1
            selected_df = pd.concat([selected_df, staples_row], ignore_index=True)


        scaled_df = build_scaled_df(selected_df, recipes_df, params)
        grocery_df = build_grocery_df(scaled_df, params, store_layout_df)


        st.session_state.plan_data = {
            "plan_df": plan_df,
            "scaled_df": scaled_df,
            "grocery_df": grocery_df,
            "selected_df": selected_df,
            "params": params,
        }


        # Reset flag so sidebar changes don't regenerate plan
        st.session_state.generate_plan = False

    # ---------------------------------------------------------
    # Always reuse frozen plan
    # ---------------------------------------------------------
    data = st.session_state.plan_data
    plan_df = data["plan_df"]
    scaled_df = data["scaled_df"]
    grocery_df = data["grocery_df"]
    selected_df = data["selected_df"]
    params = data["params"]

    # ---------------------------------------------------------
    # Tabs
    # ---------------------------------------------------------
    tab_recipes, tab_plan, tab_grocery = st.tabs(
        ["📘 Recipes", "📅 Meal Plan", "🛒 Grocery List"]
    )

    # --- Recipes Tab ---
    with tab_recipes:
        st.markdown("### Recipes in This Plan")

        card_meal_names = filter_meal_names_for_recipe_cards(
            scaled_df["Meal Name"].unique(), meals_df
        )

        def _plan_recipe_badges(recipe_name):
            """Every attribute the card shows lives in this one list now
            (previously split between badges and a separate metrics
            row) -- shared with the height calc below so its line
            count is accounted for in card sizing."""
            meta = meals_df[meals_df["Meal Name"] == recipe_name].iloc[0]
            scale_factor = selected_df[selected_df["Meal Name"] == recipe_name]["Scale Factor"].iloc[0]
            cost_value = meta["Cost per Serving"]
            formatted_cost = "N/A" if pd.isna(cost_value) else f"${float(cost_value):.2f}"
            return [
                ("🧑‍🍳 Chef", meta["Source"]),
                ("🌍 Cuisine", meta["Cuisine"]),
                ("⚖️ Scale", f"{scale_factor}×"),
                ("💰 Cost/Serving", formatted_cost),
                ("💪 Effort", meta["Effort"]),
                ("😋 Taste", meta["Taste"]),
                ("🥗 Health", meta["Healthy"]),
                ("🧊 Freezable", meta["Freezable"]),
                ("🧽 Cleanup", meta["Cleanup"]),
            ]

        # One shared sizing across BOTH the Bulk and Quick Meal groups
        # below, so the two category sections line up with each other
        # too, not just within themselves. Body is empty (these cards
        # have no reasoning text) -- the 9-line attribute list is what
        # drives height here, via extra_lines_fn.
        recipe_card_sizing = compute_card_height(
            card_meal_names,
            title_fn=lambda name: name,
            body_fn=lambda name: "",
            extra_lines_fn=lambda name: 9,
        )

        def _render_plan_recipe_card(recipe_name, rank):
            render_metadata_card(
                recipe_name,
                rank=rank,
                height=recipe_card_sizing.height,
                title_lines=recipe_card_sizing.title_lines,
                badges=_plan_recipe_badges(recipe_name),
            )

        # Group cards by category so bulk cooks (the meals driving the
        # week's leftovers) read as a distinct set from quick meals,
        # instead of one shuffled grid. Any other category that reaches
        # this tab (e.g. Frozen Leftover) falls into a trailing "Other"
        # group rather than being silently dropped.
        CATEGORY_ORDER = ["Bulk", "Quick Meal"]
        CATEGORY_LABELS = {"Bulk": "🍲 Bulk Meals", "Quick Meal": "⚡ Quick Meals"}
        name_to_category = meals_df.set_index("Meal Name")["Category"]

        grouped_names = {cat: [] for cat in CATEGORY_ORDER}
        other_names = []
        for name in card_meal_names:
            category = name_to_category.get(name)
            (grouped_names[category] if category in grouped_names else other_names).append(name)

        for category in CATEGORY_ORDER:
            names = grouped_names[category]
            if not names:
                continue
            st.markdown(f"#### {CATEGORY_LABELS[category]}")
            render_card_grid(names, _render_plan_recipe_card)

        if other_names:
            st.markdown("#### Other")
            render_card_grid(other_names, _render_plan_recipe_card)

    # --- Meal Plan Tab ---
    with tab_plan:
        st.markdown("### Weekly Meal Plan")

        SLOT_ICONS = {
            "Breakfast": "🍳",
            "Lunch": "🥪",
            "Dinner": "🍽️"
        }

        def _day_slots(day_number):
            day_df = plan_df[plan_df["Meal Day Number"] == day_number]
            return [
                {
                    "icon": SLOT_ICONS.get(row["Meal Slot"], "🍽️"),
                    "slot": row["Meal Slot"],
                    "meal_name": row["Meal Name"],
                }
                for _, row in day_df.iterrows()
            ]

        day_numbers = plan_df["Meal Day Number"].unique()
        all_days_slots = {day_number: _day_slots(day_number) for day_number in day_numbers}

        # Every day's card sized to whichever day has the most total
        # wrapped lines across its slots, so they're all the same
        # height regardless of slot count or meal-name length.
        day_card_height = compute_day_card_height(
            list(all_days_slots.values()),
            slot_text_fn=lambda slot: f"{slot['slot']}: {slot['meal_name']}",
        )

        def _render_day_card(day_number, _rank):
            # _rank is unused -- calendar days aren't a ranked list, so
            # no "1." numbering here, unlike the recipe cards above.
            day_df = plan_df[plan_df["Meal Day Number"] == day_number]
            day_name = day_df["Meal Day Name"].iloc[0]
            render_day_plan_card(day_name, all_days_slots[day_number], height=day_card_height)

        render_card_grid(
            day_numbers,
            _render_day_card,
            num_columns=3,
        )


    # --- Grocery List Tab ---
    with tab_grocery:
        st.markdown("### Grocery List")
        st.caption("Sorted by aisle order for your selected store.")

        display_cols = [
            "Section", "Ingredient Name", "Scaled Display Quantity",
            "Display Unit", "Meal Names"
        ]
        st.dataframe(
            grocery_df[display_cols],
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "Download Grocery List (CSV)",
            grocery_df[display_cols].to_csv(index=False),
            file_name="grocery_list.csv",
            mime="text/csv",
        )

    # ---------------------------------------------------------
    # Footer
    # ---------------------------------------------------------
    st.markdown("---")
    st.markdown("### Finalize or Adjust Your Plan")

    adjustment_request = st.text_area(
        "Request changes to this plan (optional)",
        placeholder="e.g., swap Tuesday dinner, reduce scale factor, add one more freezer meal..."
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Apply Changes"):
            api_key = st.session_state.get("openai_api_key")

            if not adjustment_request.strip():
                st.warning("Enter a change request above before applying.")
            elif not api_key:
                st.error("Enter your OpenAI API key in the sidebar to apply changes.")            
            else:
                st.session_state.plan_regen_counter = (
                    st.session_state.get("plan_regen_counter", 0) + 1
                )

                planner_meals_df = filter_meals_for_planner(meals_df)
                revise_workbook_json = {
                    "meals": planner_meals_df.to_dict(orient="records"),
                    "recipes": recipes_df.to_dict(orient="records"),
                    "history": history_df.to_dict(orient="records")
                }

                try:
                    with st.spinner("Reworking your plan based on your feedback..."):
                        revised_selected_df, revised_plan_df = generate_plan(
                            params,
                            revise_workbook_json,
                            api_key=api_key,
                            feedback=adjustment_request,
                            cache_bust=st.session_state.plan_regen_counter,
                        )
                except Exception as e:
                    st.error(f"Couldn't generate a plan: {e}")
                    st.session_state.generate_plan = False
                    return


                staples_row = meals_df[meals_df["Meal Name"] == "Staples"].copy()
                if not staples_row.empty:
                    staples_row["Scale Factor"] = 1
                    revised_selected_df = pd.concat(
                        [revised_selected_df, staples_row], ignore_index=True
                    )

                revised_scaled_df = build_scaled_df(revised_selected_df, recipes_df, params)
                revised_grocery_df = build_grocery_df(revised_scaled_df, params, store_layout_df)

                st.session_state.plan_data = {
                    "plan_df": revised_plan_df,
                    "scaled_df": revised_scaled_df,
                    "grocery_df": revised_grocery_df,
                   "selected_df": revised_selected_df,
                    "params": params,
                }

                st.success("Plan updated based on your feedback.")
                st.rerun()

    with col2:
        if is_owner_mode():
            save_clicked = st.button("Save Plan to Google Sheets")
        else:
            save_clicked = False
            st.download_button(
                "Download Plan (CSV)",
                plan_df.to_csv(index=False),
                file_name="meal_plan.csv",
                mime="text/csv",
            )
            st.caption("Public visitors get a download instead of writing to the owner's sheet.")

    if save_clicked:
        write_plan_to_google_sheets(plan_df, scaled_df, grocery_df, params)
        st.success("Plan saved to Google Sheets!")


def _render_browse_meals_tab(meals_df, recipes_df):
    """Browsable view over the full Meals database -- every meal in the
    sheet, independent of any generated plan. Search/filter/sort only;
    no LLM involved. Takeout entries are excluded here since they get
    their own Browse tab on the Takeout Recommender page."""
    st.caption("Everything in your meal database, searchable and browsable.")

    base_df = meals_df[meals_df["Category"].isin(["Bulk", "Quick Meal"])]

    search_cols = st.columns(2)
    with search_cols[0]:
        meal_names = sorted(n for n in base_df["Meal Name"].unique() if n)
        name_search = st.selectbox("Search by name", ["Any"] + meal_names)
    with search_cols[1]:
        ingredient_names = sorted(
            n for n in recipes_df["Ingredient Name"].unique() if n
        )
        ingredient_search = st.selectbox("Search by ingredient", ["Any"] + ingredient_names)

    filter_cols = st.columns(3)
    with filter_cols[0]:
        categories = sorted(c for c in base_df["Category"].unique() if c)
        category_filter = st.multiselect("Category", categories)
    with filter_cols[1]:
        cuisines = sorted(c for c in base_df["Cuisine"].unique() if c)
        cuisine_filter = st.multiselect("Cuisine", cuisines)
    with filter_cols[2]:
        sort_by = st.selectbox(
            "Sort by",
            [
                "Name",
                "Cost per Serving (low to high)",
                "Taste (high to low)",
                "Healthy (high to low)",
                "Effort (low to high)",
                "Stretchiness (high to low)",
                "Cleanup (low to high)",
            ],
        )

    df = base_df.copy()
    if name_search != "Any":
        df = df[df["Meal Name"] == name_search]
    if ingredient_search != "Any":
        matching_names = recipes_df[
            recipes_df["Ingredient Name"] == ingredient_search
        ]["Meal Name"].unique()
        df = df[df["Meal Name"].isin(matching_names)]
    if category_filter:
        df = df[df["Category"].isin(category_filter)]
    if cuisine_filter:
        df = df[df["Cuisine"].isin(cuisine_filter)]

    if sort_by == "Cost per Serving (low to high)":
        df = df.sort_values("Cost per Serving", ascending=True, na_position="last")
    elif sort_by == "Taste (high to low)":
        df = df.sort_values("Taste", ascending=False, na_position="last")
    elif sort_by == "Healthy (high to low)":
        df = df.sort_values("Healthy", ascending=False, na_position="last")
    elif sort_by == "Effort (low to high)":
        df = df.sort_values("Effort", ascending=True, na_position="last")
    elif sort_by == "Stretchiness (high to low)":
        df = df.sort_values("Stretchiness", ascending=False, na_position="last")
    elif sort_by == "Cleanup (low to high)":
        df = df.sort_values("Cleanup", ascending=True, na_position="last")
    else:
        df = df.sort_values("Meal Name")

    st.caption(f"{len(df)} meal{'s' if len(df) != 1 else ''}")
    if df.empty:
        st.info("No meals match those filters.")
        return

    def _format_score(value):
        return "N/A" if pd.isna(value) else f"{value:g}"

    def _truncate_title(name, max_len=20):
        # A couple of meal names (e.g. "Salad Kit and Rotisserie
        # Chicken") wrap to two lines and stretch just that card.
        # Almost everything else here is one line, so reserving
        # two-line height for the whole grid wastes space -- easier
        # to just shorten the rare long ones.
        if len(name) <= max_len:
            return name
        return name[: max_len - 1].rstrip() + "…"

    def _render_browse_meal_card(meal, _rank):
        # _rank is unused -- this is a browsable catalog, not a ranked
        # list, same as the Cocktail page's My Bar cards.
        cost_value = meal["Cost per Serving"]
        formatted_cost = "N/A" if pd.isna(cost_value) else f"${float(cost_value):.2f}"

        badges = [b for b in [meal["Category"], meal["Cuisine"]] if b] + [
            ("💰 Cost/Serving", formatted_cost),
            ("💪 Effort", _format_score(meal["Effort"])),
            ("😋 Taste", _format_score(meal["Taste"])),
            ("🥗 Healthy", _format_score(meal["Healthy"])),
            ("🧊 Freezable", _format_score(meal["Freezable"])),
            ("🍲 Stretchiness", _format_score(meal["Stretchiness"])),
            ("🧽 Cleanup", _format_score(meal["Cleanup"])),
        ]

        recipe_lines = recipes_df[recipes_df["Meal Name"] == meal["Meal Name"]]
        expander_lines = [
            f"- {line['Display Quantity']} {line['Display Unit']} {line['Ingredient Name']}"
            for _, line in recipe_lines.iterrows()
        ]

        render_metadata_card(
            _truncate_title(meal["Meal Name"]),
            badges=badges,
            expander=("Ingredients", expander_lines) if expander_lines else None,
        )

    render_card_grid(df.to_dict(orient="records"), _render_browse_meal_card)