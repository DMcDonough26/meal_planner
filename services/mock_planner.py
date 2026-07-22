import pandas as pd
from services.google_sheets_loader import load_workbook

def mock_generate_plan(params):
    # Load workbook
    (
        meals_df,
        ingredients_df,
        recipes_df,
        store_layout_df,
        history_df,
        weekly_plan_df,
        grocery_list_df
    ) = load_workbook()

    # ---------------------------------------------------------
    # 1. Build selected_df (canonical schema)
    # ---------------------------------------------------------
    n_days = params["days"]
    meals_per_day = params["meals_per_day"]
    total_meals = n_days * meals_per_day

    # If not enough meals exist, repeat the list
    if len(meals_df) == 0:
        raise ValueError("Meals sheet is empty — cannot generate plan.")

    repeats = (total_meals // len(meals_df)) + 1
    expanded_meals = pd.concat([meals_df] * repeats, ignore_index=True)

    selected = expanded_meals.head(total_meals).copy()

    selected_df = selected[["Meal ID", "Meal Name"]].copy()
    selected_df["Batches"] = 1  # deterministic

    # ---------------------------------------------------------
    # 2. Build plan_df (canonical schema)
    # ---------------------------------------------------------
    plan_rows = []
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    idx = 0
    for day_num in range(1, n_days + 1):
        for slot in ["Breakfast", "Lunch", "Dinner"][:meals_per_day]:
            meal = selected.iloc[idx]
            idx += 1

            plan_rows.append({
                "Meal Day Number": day_num,
                "Meal Day Name": day_names[(day_num - 1) % 7],
                "Meal Slot": slot,
                "Meal ID": meal["Meal ID"],
                "Meal Name": meal["Meal Name"],
                "Leftover Indicator": "No",
                "Notes": ""
            })

    plan_df = pd.DataFrame(plan_rows)

    return selected_df, plan_df
