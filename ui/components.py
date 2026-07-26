import streamlit as st
import pandas as pd

from config.constants import is_owner_mode


def openai_api_key_input():
    """
    Sidebar field for the OpenAI API key. Pre-fills from st.secrets only
    in owner mode -- public visitors always see a blank, required field,
    and the app never falls back to the owner's key on their behalf.
    """
    st.sidebar.markdown("---")
    st.sidebar.subheader("OpenAI API Key")

    default_key = ""
    if is_owner_mode():
        default_key = st.secrets.get("openai", {}).get("OPENAI_API_KEY", "")

    api_key = st.sidebar.text_input(
        "Enter your OpenAI API key",
        value=default_key,
        type="password",
        help="Used only for this session's requests -- never stored or logged."
    )

    if not api_key:
        st.sidebar.warning(
            "An OpenAI API key is required to generate recommendations."
        )

    return api_key or None

def sidebar_section(title: str):
    st.sidebar.markdown(f"### {title}")
    st.sidebar.markdown("---")

def planning_controls(meals_df: pd.DataFrame, store_layout_df):
    # -----------------------------
    # Section: Planning Basics
    # -----------------------------
    sidebar_section("Planning Basics")

    days = st.sidebar.number_input("Days to plan", min_value=1, max_value=7, value=7)

    plan_start_day = st.sidebar.selectbox(
        "Plan starts on",
        ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        index=0
    )

    with st.sidebar:
        meal_pattern = st.selectbox(
            "Meals per day",
            ["Breakfast + Lunch + Dinner","Lunch + Dinner","Dinner only"]
        )

        MEAL_PATTERN_MAP = {
            "Breakfast + Lunch + Dinner": 3,
            "Lunch + Dinner": 2,
            "Dinner only": 1
        }

        meals_per_day = MEAL_PATTERN_MAP[meal_pattern]

    servings_per_meal = st.sidebar.number_input(
        "Servings per meal", min_value=1, max_value=10, value=3
    )

    bulk_cooks = st.sidebar.number_input("Number of bulk cooks", min_value=1, max_value=7, value=2)

    souper_target = st.sidebar.selectbox(
        "Souper Cubes Target (extra servings to freeze)",
        [0, 4, 8],
        index=1
    )

    store_name = st.sidebar.selectbox(
        "Which store are you shopping at?",
        store_layout_df["Store"].unique()
    )

    st.sidebar.markdown("")

    # -----------------------------
    # Section: Priorities
    # -----------------------------
    sidebar_section("Priorities")

    priorities = st.sidebar.multiselect(
        "What matters most this week?",
        [
            "Stretchiness",
            "Effort",
            "Cleanup",
            "Health",
            "Taste",
            "Freezable",
            "Cost"
        ],
        default=["Stretchiness","Effort"]
    )

    st.sidebar.markdown("")

    # -----------------------------
    # Section: Preferences
    # -----------------------------
    sidebar_section("Preferences")

    cuisine = st.sidebar.multiselect(
        "Cuisine preferences",
        ["Any"] + sorted(meals_df["Cuisine"].dropna().unique()),
        default=["Any"]
    )


    st.sidebar.markdown("")

    # -----------------------------
    # Section: Notes
    # -----------------------------
    sidebar_section("Notes / Constraints")

    notes = st.sidebar.text_area(
        "Notes (optional)",
        placeholder="e.g., avoid spicy, use up chicken thighs, guests on Thursday..."
    )

    st.sidebar.markdown("")

    # -----------------------------
    # Section: Generate
    # -----------------------------
    sidebar_section("Generate Plan")

    if st.sidebar.button("Generate Plan"):
        st.session_state.generate_plan = True
        st.session_state.plan_regen_counter = st.session_state.get("plan_regen_counter", 0) + 1

    # -----------------------------
    # Section: Calculate
    # -----------------------------

    if meals_per_day == 3:
        meal_slots = ["Breakfast", "Lunch", "Dinner"]
    elif meals_per_day == 2:
        meal_slots = ["Lunch", "Dinner"]
    else:
        meal_slots = ["Dinner"]


    total_meals = days * meals_per_day
    total_servings_consumed = total_meals * servings_per_meal
    total_servings_needed = total_servings_consumed + souper_target

    plan_date = pd.Timestamp.today().strftime("%Y-%m-%d")


    return {
        "days": days,
        "plan_start_day": plan_start_day,
        "meals_per_day": meals_per_day,
        "servings_per_meal": servings_per_meal,
        "bulk_cooks": bulk_cooks,
        "priorities": priorities,
        "cuisine": cuisine,
        "souper_target": souper_target,
        "store_name": store_name,
        "notes": notes,
        "meal_slots": meal_slots,
        "total_meals": total_meals,
        "total_servings_consumed": total_servings_consumed,
        "total_servings_needed": total_servings_needed,
        "plan_date": plan_date
    }

def takeout_controls(meals_df):
    st.sidebar.header("Takeout Preferences")

    # -----------------------------
    # Location anchor
    # -----------------------------
    location_anchor = st.sidebar.text_input(
        "Location (for distance estimates)",
        value="West County Center, St. Louis"
    )

    # -----------------------------
    # How many recommendations?
    # -----------------------------
    num_recs = st.sidebar.number_input(
        "How many recommendations?",
        min_value=1,
        max_value=10,
        value=3
    )

    # -----------------------------
    # Cuisine preferences
    # -----------------------------
    sidebar_section("Cuisine Preferences")

    cuisines = st.sidebar.multiselect(
        "Which cuisines are you open to?",
        ["Any"] + sorted(meals_df["Cuisine"].dropna().unique()),
        default=["Any"]
    )

    # -----------------------------
    # Required features
    # -----------------------------
    sidebar_section("Required Features")

    delivery = st.sidebar.checkbox("Delivery")
    drive_thru = st.sidebar.checkbox("Drive-thru")
    healthy = st.sidebar.checkbox("Healthy options")
    cheap = st.sidebar.checkbox("Budget-friendly")
    stretchy = st.sidebar.checkbox("Good leftovers / stretchiness")

    # -----------------------------
    # Source preference
    # -----------------------------
    sidebar_section("Source Preference")

    source_pref = st.sidebar.selectbox(
        "Where should recommendations come from?",
        [
            "Existing takeout options only",
            "New suggestions only"
        ]
    )

    # -----------------------------
    # Free-form notes
    # -----------------------------
    sidebar_section("Notes")

    notes = st.sidebar.text_area(
        "Anything else?",
        placeholder="e.g., something spicy, something that reheats well, avoid fried foods..."
    )

    # -----------------------------
    # Generate button
    # -----------------------------
    generate = st.sidebar.button("Recommend Takeout")

    return {
        "num_recs": num_recs,
        "cuisines": cuisines,
        "delivery": delivery,
        "drive_thru": drive_thru,
        "healthy": healthy,
        "cheap": cheap,
        "stretchy": stretchy,
        "source_pref": source_pref,
        "notes": notes,
        "location_anchor": location_anchor,
        "generate": generate
    }


def table_section(title: str, df):
    import streamlit as st
    st.markdown(f"### {title}")
    st.dataframe(df, use_container_width=True)
    st.markdown("")  # spacing

def recipe_card(recipe_name: str, metadata: dict):
    """
    Render a clean, minimal recipe preview card.
    metadata example:
    {
        "Cuisine": "Mexican",
        "Taste": 8,
        "Health": 6,
        "Stretchiness": 9,
        "Cleanup": 4,
        "Cost": "$",
        "Freezable": "Yes"
    }
    """
    with st.container(border=True):
        st.markdown(f"#### {recipe_name}")

        cols = st.columns(2)
        for i, (key, value) in enumerate(metadata.items()):
            with cols[i % 2]:
                st.markdown(f"**{key}:** {value}")

def recipe_ideas_controls(meals_df):
    """
    Sidebar controls for the Recipe Ideas page. Deliberately lighter than
    planning_controls -- this mode doesn't need days/servings/bulk-cook
    params, since ideas aren't scaled or turned into a grocery list.
    """
    st.sidebar.header("Recipe Idea Preferences")

    cuisines = st.sidebar.multiselect(
        "Cuisines you're interested in",
        sorted(meals_df["Cuisine"].dropna().unique().tolist())
    )

    ingredients_on_hand = st.sidebar.text_area(
        "Ingredients you'd like to use (optional)",
        placeholder="e.g. chicken thighs, fresh basil, canned chickpeas"
    )

    num_ideas = st.sidebar.number_input(
        "How many ideas?",
        min_value=1,
        max_value=10,
        value=3
    )

    notes = st.sidebar.text_area(
        "Anything else? (optional)",
        placeholder="e.g. nothing too spicy, quick weeknight options, vegetarian"
    )

    generate = st.sidebar.button("Suggest Recipe Ideas")

    return {
        "cuisines": cuisines,
        "ingredients_on_hand": ingredients_on_hand,
        "num_ideas": num_ideas,
        "notes": notes,
        "generate": generate
    }


def recipe_idea_card(name: str, source: str, link, blurb: str):
    """
    Render a recipe-idea suggestion card. Unlike recipe_card, this has no
    numeric cookbook metadata -- ideas are idea-only (see
    RECIPE_IDEAS_SYSTEM_PROMPT), so the card is title + source + optional
    link + a free-text blurb instead of a label/value grid.
    """
    with st.container(border=True):
        st.markdown(f"#### {name}")
        st.caption(f"Source: {source}")
        if link:
            st.markdown(f"[View recipe]({link})")
        st.write(blurb)
