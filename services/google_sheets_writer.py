import pandas as pd
import gspread
import streamlit as st
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
    sheet.clear()
    header = list(df.columns)
    rows = df.astype(str).values.tolist()
    sheet.update([header] + rows)

def _append_rows(sheet, df: pd.DataFrame):
    """Append DataFrame rows to the bottom of a sheet."""
    rows = df.astype(str).values.tolist()
    for row in rows:
        sheet.append_row(row)

# ---------------------------------------------------------
# Main entry point called by your button
# ---------------------------------------------------------

def write_plan_to_google_sheets(
    plan_df: pd.DataFrame,
    scaled_df: pd.DataFrame,
    grocery_df: pd.DataFrame,
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
    # Expected grocery_df columns:
    # Section, Ingredient Name, Quantity, Unit (optional), Recipe IDs (optional)
    grocery_export = pd.DataFrame({
        "Plan Date": plan_date,
        "Store": grocery_df["Store"],
        "Section": grocery_df["Section"],
        "Order Number": grocery_df.get("Order Number", ""),   # new
        "Ingredient ID": grocery_df.get("Ingredient ID", ""),
        "Ingredient Name": grocery_df["Ingredient Name"],
        "Scaled Display Quantity": grocery_df["Scaled Display Quantity"],
        "Display Unit": grocery_df["Display Unit"],
        "Meal Names": grocery_df.get("Meal Names", ""),
        "Notes": "",
    })


    # ---------------------------------------------------------
    # Write Weekly Grocery List (overwrite)
    # ---------------------------------------------------------
    grocery_sheet = _get_sheet("Weekly Grocery List")
    _overwrite_sheet(grocery_sheet, grocery_export)
