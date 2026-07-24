import streamlit as st
import pandas as pd
from ui.layout import page_header
from ui.components import (
    planning_controls,
    table_section,
    recipe_card
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
    # If user has not clicked Generate Plan yet
    # ---------------------------------------------------------
    if "generate_plan" not in st.session_state:
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

        selected_df, plan_df = generate_plan(
            params,
            workbook_json,
            api_key=api_key,
            cache_bust=st.session_state.get("plan_regen_counter", 0),
        )

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

        for recipe_name in card_meal_names:
            meta = meals_df[meals_df["Meal Name"] == recipe_name].iloc[0]

            scale_factor = selected_df[selected_df["Meal Name"] == recipe_name]["Scale Factor"].iloc[0]

            cost_value = meta["Cost per Serving"]
            formatted_cost = "N/A" if pd.isna(cost_value) else f"${float(cost_value):.2f}"

            recipe_card(
                recipe_name,
                {
                    "Cuisine": meta["Cuisine"],
                    "Source": meta["Source"],
                    "Status": "Existing",
                    "Effort": meta["Effort"],
                    "Taste": meta["Taste"],
                    "Health": meta["Healthy"],
                    "Stretchiness": meta["Stretchiness"],
                    "Cleanup": meta["Cleanup"],
                    "Cost per Serving": formatted_cost,
                    "Freezable": meta["Freezable"],
                    "Scale Factor": f"{scale_factor}×",
                }
            )

            st.markdown("")

    # --- Meal Plan Tab ---
    with tab_plan:
        st.markdown("### Weekly Meal Plan")

        SLOT_ICONS = {
            "Breakfast": "🍳",
            "Lunch": "🥪",
            "Dinner": "🍽️"
        }

        for day in plan_df["Meal Day Number"].unique():
            day_df = plan_df[plan_df["Meal Day Number"] == day]

            day_name = day_df["Meal Day Name"].iloc[0]
            st.subheader(f"{day_name} (Day {day})")


            cols = st.columns(len(day_df))
            for col, (_, row) in zip(cols, day_df.iterrows()):
                icon = SLOT_ICONS.get(row["Meal Slot"], "🍽️")
                with col:
                    st.markdown(f"**{icon} {row['Meal Slot']}**")
                    st.markdown(row["Meal Name"])


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

                revised_selected_df, revised_plan_df = generate_plan(
                    params,
                    revise_workbook_json,
                    api_key=api_key,
                    feedback=adjustment_request,
                    cache_bust=st.session_state.plan_regen_counter,
                )

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
