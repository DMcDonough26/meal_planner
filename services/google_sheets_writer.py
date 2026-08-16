import pandas as pd
import gspread
import streamlit as st
import re
from google.oauth2.service_account import Credentials
from config.constants import SHEET_NAME

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def _get_client():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES
    )
    return gspread.authorize(creds)

def _get_sheet(tab_name: str):
    client = _get_client()
    workbook = client.open(SHEET_NAME)
    return workbook.worksheet(tab_name)

def _overwrite_sheet(sheet, df: pd.DataFrame):
    """Clear a sheet and write header + rows from a DataFrame."""
    header = list(df.columns)
    # fillna first: NaN/None (e.g. an unmatched Store Layout section's blank
    # Order Number) is not valid JSON and gets rejected client-side by the
    # Sheets API client -- turning it into an empty string keeps that safe.
    rows = df.fillna("").astype(str).values.tolist()
    # Only clear once the payload is known-good, so a bad value can't leave
    # the sheet wiped with nothing written back in its place.
    sheet.clear()
    sheet.update([header] + rows)

def _append_rows(sheet, df: pd.DataFrame):
    """Append DataFrame rows to the bottom of a sheet."""
    rows = df.fillna("").astype(str).values.tolist()
    for row in rows:
        sheet.append_row(row)

# ---------------------------------------------------------
# Main entry point called by your button
# ---------------------------------------------------------

def write_plan_to_google_sheets(
    plan_df: pd.DataFrame,
    scaled_df: pd.DataFrame,
    grocery_df: pd.DataFrame,
    selected_df: pd.DataFrame,
    params: dict
):

    # ---------------------------------------------------------
    # Compute weekday mapping based on plan_start_day
    # ---------------------------------------------------------
    start_day = params.get("plan_start_day", "Monday")
    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    start_index = weekday_order.index(start_day)

    def compute_weekday(day_number):
        return weekday_order[(start_index + day_number - 1) % 7]

    plan_date = pd.Timestamp.now().strftime("%Y-%m-%d")

    # ---------------------------------------------------------
    # Batches per Meal ID (this is the "Scale Factor" shown on the
    # Recipes tab's "⚖️ Scale" badge). selected_df can have the same
    # Meal ID repeated (e.g. it's built from a merge upstream), so
    # dedupe down to one Scale Factor per Meal ID before joining --
    # every occurrence of a meal in the week shares the same batch
    # count, there's no per-slot scaling.
    # ---------------------------------------------------------
    batches_lookup = (
        selected_df[["Meal ID", "Scale Factor"]]
        .drop_duplicates(subset="Meal ID")
        .rename(columns={"Scale Factor": "Batches"})
    )

    # ---------------------------------------------------------
    # Build Weekly Meal Plan export (new schema)
    # ---------------------------------------------------------
    weekly_plan_export = pd.DataFrame({
        "Plan Date": plan_date,
        "Meal Day Number": plan_df["Meal Day Number"],
        "Meal Day": plan_df["Meal Day Name"],
        "Meal Slot": plan_df["Meal Slot"],
        "Meal ID": plan_df["Meal ID"],
        "Recipe Name": plan_df["Meal Name"],
        "Leftover Indicator": plan_df["Leftover Indicator"],
        "Notes": ""
    })

    weekly_plan_export = weekly_plan_export.merge(batches_lookup, on="Meal ID", how="left")
    weekly_plan_export = weekly_plan_export[
        [
            "Plan Date", "Meal Day Number", "Meal Day", "Meal Slot", "Meal ID",
            "Recipe Name", "Batches", "Leftover Indicator", "Notes",
        ]
    ]

    # ---------------------------------------------------------
    # Write Weekly Meal Plan (overwrite)
    # ---------------------------------------------------------
    weekly_plan_sheet = _get_sheet("Weekly Meal Plan")
    _overwrite_sheet(weekly_plan_sheet, weekly_plan_export)

    # ---------------------------------------------------------
    # Build History export (same schema as Weekly Meal Plan)
    # ---------------------------------------------------------
    history_export = weekly_plan_export.copy()

    # ---------------------------------------------------------
    # Append History rows
    # ---------------------------------------------------------
    history_sheet = _get_sheet("History")
    _append_rows(history_sheet, history_export)

    # ---------------------------------------------------------
    # Build Weekly Grocery List export (new schema)
    # ---------------------------------------------------------
    grocery_export = pd.DataFrame({
        "Plan Date": plan_date,
        "Store": grocery_df["Store"],
        "Section": grocery_df["Section"],
        "Scaled Display Quantity": grocery_df["Scaled Display Quantity"],
        "Display Unit": grocery_df["Display Unit"],
        "Ingredient Name": grocery_df["Ingredient Name"],
        "Meal Names": grocery_df.get("Meal Names", ""),
    })


    # ---------------------------------------------------------
    # Write Weekly Grocery List (overwrite)
    # ---------------------------------------------------------
    grocery_sheet = _get_sheet("Weekly Grocery List")
    _overwrite_sheet(grocery_sheet, grocery_export)

# ---------------------------------------------------------
# Recipe Ideas -> Cookbook write-back
# ---------------------------------------------------------

def _generate_next_meal_id(meals_df: pd.DataFrame) -> str:
    """Generate the next Meal ID by incrementing the highest numeric suffix
    found among existing IDs, reusing that ID's non-numeric prefix (e.g.
    "M014" -> "M015"). Falls back to a plain sequential number if no
    existing IDs parse."""
    existing_ids = meals_df["Meal ID"].dropna().astype(str)
    best_prefix, best_num, best_width = "", 0, 0
    for mid in existing_ids:
        match = re.match(r"^(\D*)(\d+)$", mid.strip())
        if match:
            prefix, num_str = match.groups()
            num = int(num_str)
            if num > best_num:
                best_num, best_prefix, best_width = num, prefix, len(num_str)
    if best_width:
        return f"{best_prefix}{str(best_num + 1).zfill(best_width)}"
    return str(len(existing_ids) + 1)

def write_recipe_idea_to_cookbook(idea: dict, category: str, meals_df: pd.DataFrame) -> str:
    """
    Append a Recipe Ideas card to the Meals sheet as a new cookbook entry.
    Only Meal Name/ID/Category/Source/References/Notes are populated --
    ranking-attribute fields (Cook Time, Effort, Cost, etc.) are left as
    "TBD" since new ideas intentionally skip the ranking-attribute
    estimation used elsewhere; the user fills those in after actually
    cooking it. Returns the new Meal ID.
    """
    new_id = _generate_next_meal_id(meals_df)
    row = {col: "TBD" for col in meals_df.columns}
    row["Meal Name"] = idea.get("Name", "")
    row["Meal ID"] = new_id
    row["Category"] = category
    row["Source"] = idea.get("Source", "")
    row["References"] = idea.get("Link", "")
    row["Notes"] = idea.get("Blurb", "")
    row_df = pd.DataFrame([row], columns=meals_df.columns)

    sheet = _get_sheet("Meals")
    _append_rows(sheet, row_df)
    return new_id
