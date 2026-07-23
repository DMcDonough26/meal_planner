"""
Central place for "which meals go where" logic.

Keeping this in one module means the planner LLM payload and the
Recipes tab display always agree on what counts as a real, selectable
meal vs. a category that's either handled elsewhere in the app
(Staples) or purely conceptual in the LLM's output (Takeout, which the
system prompt already represents as a literal string with no recipe).
"""

# Categories the planner LLM is allowed to choose from.
# - Staples is excluded: it's force-included by plan_page.py regardless
#   of what the LLM returns, so sending it just costs tokens.
# - Takeout is excluded: the system prompt already tells the LLM to
#   emit "Takeout" as a literal plan_df string with no Meal ID/recipe,
#   so there's nothing for it to select from meals_df.
# - Breakfast is excluded: not currently used by the planner.
PLANNER_SELECTABLE_CATEGORIES = ["Bulk", "Quick Meal", "Frozen Leftover"]

# Categories that should never appear as a "Recipe" card, even if they
# end up in scaled_df for some other reason.
RECIPE_CARD_EXCLUDED_CATEGORIES = ["Staples"]


def filter_meals_for_planner(meals_df):
    """Meals actually sent to the meal-planner LLM call."""
    return meals_df[meals_df["Category"].isin(PLANNER_SELECTABLE_CATEGORIES)]


def filter_meal_names_for_recipe_cards(meal_names, meals_df):
    """
    Given an iterable of Meal Names (e.g. scaled_df["Meal Name"].unique()),
    return only the ones that should render as a recipe card.
    """
    excluded = set(
        meals_df[meals_df["Category"].isin(RECIPE_CARD_EXCLUDED_CATEGORIES)]["Meal Name"]
    )
    return [name for name in meal_names if name not in excluded]