
import streamlit as st
import pandas as pd
from services.google_sheets_loader import _get_client

COCKTAIL_SHEET_NAMES = {
    "cocktails": "Cocktails",
    "cocktail_ingredients": "Cocktail Ingredients",  # ingredient master (was "Bar Inventory")
    "cocktail_recipes": "Cocktail Recipes",          # recipe/ingredient junction (was "Cocktail Ingredients")
}

@st.cache_data
def read_cocktail_sheet(sheet_name: str) -> pd.DataFrame:
    """Reads a single named worksheet into a DataFrame.
    Mirrors google_sheets_loader.py's read_sheet pattern, but kept
    separate so cocktail-sheet changes can't affect meal-planner caching.
    """
    client = _get_client()
    ws = client.open("Meal Plan for Web App").worksheet(sheet_name)
    records = ws.get_all_records()
    return pd.DataFrame(records)


@st.cache_data
def load_cocktails() -> pd.DataFrame:
    return read_cocktail_sheet(COCKTAIL_SHEET_NAMES["cocktails"])


def load_cocktail_ingredients(is_owner: bool) -> pd.DataFrame:
    """Ingredient master list. Owner mode: On-Hand reflects the real
    persisted sheet values. Non-owner: On-Hand is overridden with the
    sheet's own Guest Default On-Hand column, since non-owner visitors
    have no persisted inventory of their own.
    """
    df = read_cocktail_sheet(COCKTAIL_SHEET_NAMES["cocktail_ingredients"])
    if not is_owner:
        df = df.copy()
        df["On-Hand"] = df["Guest Default On-Hand"]
    return df


@st.cache_data
def load_cocktail_recipes() -> pd.DataFrame:
    return read_cocktail_sheet(COCKTAIL_SHEET_NAMES["cocktail_recipes"])


def load_cocktail_workbook(is_owner: bool) -> dict:
    """Single entry point the cocktail page calls — same shape convention
    as the meal planner's load_workbook, but its own separate function."""
    return {
        "cocktails": load_cocktails(),
        "cocktail_ingredients": load_cocktail_ingredients(is_owner),
        "cocktail_recipes": load_cocktail_recipes(),
    }