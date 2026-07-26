import streamlit as st
from services.cocktail_sheets_loader import load_cocktail_workbook
from services.cocktail_llm_client import generate_cocktail_plan

def render_cocktail_planner_page():
    st.title("Cocktail Planner")

    # Matches the flag set in app.py's Owner Access expander.
    is_owner = st.session_state.get("owner_unlocked", False)
    workbook = load_cocktail_workbook(is_owner)
    cocktail_ingredients_df = workbook["cocktail_ingredients"]

    with st.sidebar:
        st.header("Cocktail Plan Settings")

        recipe_source = st.radio(
            "Existing recipes or something new?",
            options=["Existing recipes", "New recipes"]
        )

        st.caption("How to handle missing ingredients?")
        missing_ingredient_handling = st.radio(
            "Missing ingredients",
            options=[
                "Only show me recipes where I have exactly everything",
                "I'm ok with using substitutes I have on-hand",
                "Show me recipes even if I'm missing ingredients — I'll shop later",
            ],
            label_visibility="collapsed",
        )

        party_size = st.radio(
            "How many people?",
            options=["1", "2-4", "5+"],
            horizontal=True,
        )

        st.subheader("Vibe")
        drink_style = st.multiselect(
            "Drink style",
            options=[
                "Fancy cocktails",
                "Beach drinks",
                "Mixed drinks",
            ],
        )
        occasion = st.multiselect(
            "Occasion",
            options=[
                "Daytime party",
                "Happy hour",
                "Nightcap",
            ],
        )

    # Inventory lives on the main page body, not the sidebar — too many
    # toggles to be usable squeezed into a narrow column.
    st.subheader("Current Inventory")
    st.caption("What do you have and want to drink right now?")

    selected_inventory = []
    categories = cocktail_ingredients_df["Category"].unique()
    NUM_COLUMNS = 5
    columns = st.columns(NUM_COLUMNS)
    for i, category in enumerate(categories):
        with columns[i % NUM_COLUMNS]:
            with st.expander(category):
                category_items = cocktail_ingredients_df[cocktail_ingredients_df["Category"] == category]
                for _, row in category_items.iterrows():
                    item_name = row["Ingredient Name"]
                    checked = st.toggle(
                        item_name,
                        value=(row["On-Hand"] == "Yes"),
                        key=f"inv_{category}_{item_name}",
                    )
                    if checked:
                        selected_inventory.append(item_name)

    st.divider()

    situational_context = st.text_area(
        "Anything else? (occasion, mood, a bottle you're curious about, etc.)",
        placeholder="e.g. Curious about the Averna I bought last month...",
    )

    generate_clicked = st.button("Get Recommendations", type="primary")

    if generate_clicked:
        # NOTE: assuming the API key lives in session_state under this key,
        # mirroring the meal planner's api_key param -- swap this for
        # whatever the real mechanism is if it's named differently.
        api_key = st.session_state.get("openai_api_key")

        params = {
            "recipe_source": recipe_source,
            "missing_ingredient_handling": missing_ingredient_handling,
            "party_size": party_size,
            "drink_style": drink_style,
            "occasion": occasion,
            "selected_inventory": selected_inventory,
            "situational_context": situational_context,
        }

        workbook_json = {
            "cocktails": workbook["cocktails"].to_dict(orient="records"),
            "cocktail_ingredients": workbook["cocktail_ingredients"].to_dict(orient="records"),
            "cocktail_recipes": workbook["cocktail_recipes"].to_dict(orient="records"),
        }

        cache_bust = st.session_state.get("cocktail_cache_bust", 0)
        st.session_state["cocktail_cache_bust"] = cache_bust + 1

        try:
            cocktails = generate_cocktail_plan(
                params, workbook_json, api_key, cache_bust=cache_bust
            )
        except ValueError as e:
            st.error(str(e))
            cocktails = None

        response = {"cocktails": cocktails} if cocktails is not None else None

        if response:
            st.subheader("Recommendations")
            for cocktail in response["cocktails"]:
                with st.container(border=True):
                    st.markdown(f"### {cocktail['name']}")
                    st.caption(f"{cocktail['source'].capitalize()} recipe · Effort: {cocktail['effort']}")
                    st.write(cocktail["why"])

                    st.markdown("**Ingredients**")
                    for ing in cocktail["ingredients"]:
                        marker = "✅" if ing["on_hand"] else "🛒"
                        line = f"{marker} {ing['amount']} {ing['item']}"
                        if ing.get("note"):
                            line += f"  \n*{ing['note']}*"
                        st.write(line)

                    st.caption(f"Batch note: {cocktail['batch_note']}")

    else:
        st.info("Choose your inventory above, set preferences in the sidebar, and click **Get Recommendations**.")