import pandas as pd
import gspread
import streamlit as st
from google.oauth2.service_account import Credentials
from config.constants import SHEET_NAME

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def _get_client():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES
    )
    return gspread.authorize(creds)

def _read_sheet(workbook, tab_name):
    sheet = workbook.worksheet(tab_name)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def _convert_numeric(df, numeric_cols):
    """Convert selected columns to numeric, coercing errors to NaN."""
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

def _safe_numeric(series):
    return (
        series.astype(str)
        .str.replace("$", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.replace("½", "0.5", regex=False)
        .str.replace("¼", "0.25", regex=False)
        .str.replace("¾", "0.75", regex=False)
        .str.extract(r"([0-9]*\.?[0-9]+)")  # extract numeric portion
        .astype(float)
    )

@st.cache_data(ttl=300, show_spinner=False)
def load_workbook():
    client = _get_client()
    workbook = client.open(SHEET_NAME)

    # Meals
    meals_df = _read_sheet(workbook, "Meals")

    meals_df["Cost"] = _safe_numeric(meals_df["Cost"])
    meals_df["Cost per Serving"] = _safe_numeric(meals_df["Cost per Serving"])

    meals_df = _convert_numeric(
        meals_df,
        [
            "Cook Time", "Servings", "Time Per Serving", "Stretchiness",
            "Effort", "Cleanup", "Healthy", "Taste", "Freezable",
            "Cost", "Cost per Serving", "Drive Thru", "Delivery"
        ]
    )

    # Ingredients
    ingredients_df = _read_sheet(workbook, "Ingredients")

    ingredients_df["Price"] = _safe_numeric(ingredients_df["Price"])

    ingredients_df = _convert_numeric(
        ingredients_df,
        ["Ingredient ID", "Quantity", "Price"]
    )

    # Recipes
    recipes_df = _read_sheet(workbook, "Recipes")

    recipes_df["Price"] = _safe_numeric(recipes_df["Price"])
    recipes_df["Portion Used"] = _safe_numeric(recipes_df["Portion Used"])/100
    recipes_df["Cost Used"] = _safe_numeric(recipes_df["Cost Used"])

    recipes_df = _convert_numeric(
        recipes_df,
        [
            "Ingredient ID", "Quantity", "Price",
            "Portion Used", "Cost Used"
        ]
    )



    # Store Layout
    store_layout_df = _read_sheet(workbook, "Store Layout")
    store_layout_df = _convert_numeric(
        store_layout_df,
        ["Order Number"]
    )

    # History (optional normalization)
    history_df = _read_sheet(workbook, "History")

    # Weekly Plan (optional normalization)
    weekly_plan_df = _read_sheet(workbook, "Weekly Meal Plan")

    # Grocery List (optional normalization)
    grocery_list_df = _read_sheet(workbook, "Weekly Grocery List")

    return (
        meals_df,
        ingredients_df,
        recipes_df,
        store_layout_df,
        history_df,
        weekly_plan_df,
        grocery_list_df
    )