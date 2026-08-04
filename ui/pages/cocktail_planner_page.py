import random
import streamlit as st
import pandas as pd
from services.cocktail_sheets_loader import load_cocktail_workbook
from services.cocktail_llm_client import generate_cocktail_plan
from ui.layout import page_header
from ui.components import sidebar_page_header, sidebar_section, render_metadata_card, compute_card_height


CATEGORY_GROUPS = {
    "Spirits & Wines": {
        "Spirits": {"column": "Family", "values": ["Whiskey", "Rum", "Gin", "Vodka", "Tequila & Mezcal", "Brandy", "Other"]},
        "Wines": {"column": "Category", "values": ["Fortified Wine", "Aperitif Wine", "Sparkling Wine", "Wine"]},
    },
    "Liqueurs, Amari & Bitters": {
        "Liqueur": {"column": "Category", "values": ["Liqueur"]},
        "Amaro": {"column": "Category", "values": ["Amaro"]},
        "Aperitivo": {"column": "Category", "values": ["Aperitivo"]},
        "Bitters": {"column": "Category", "values": ["Bitters"]},
    },
    "Mixers": {
        "Soft Drinks": {"column": "Category", "values": ["Mixer"]},
        "Juice": {"column": "Category", "values": ["Juice"]},
        "Dairy": {"column": "Category", "values": ["Dairy"]},
        "Coffee": {"column": "Category", "values": ["Coffee"]},
    },
    "Pantry": {
        # Bar Garnish lands here now -- jarred/shelf-stable goods, same
        # aisle logic as Condiment/Preserve, not a produce item.
        "Pantry": {"column": "Category", "values": ["Condiment", "Sweetener", "Syrup", "Puree", "Preserve", "Bar Garnish"]},
    },
    "Produce": {
        # Garnish is gone from here -- what's left is genuinely fresh.
        "Produce": {"column": "Category", "values": ["Fruit", "Herb"]},
    },
}

def _render_ingredient_toggles(df, column, value, is_owner, selected_inventory):
    """Renders alphabetized on-hand toggles for one Category/Family value.
    When the "Show common ingredients only" checkbox is on, niche
    (Common != Yes) items are hidden from view -- but if one is already
    toggled on (or on-hand for the owner), it still counts toward
    selected_inventory so the filter never silently drops something the
    user already told the app they have."""
    show_common_only = st.session_state.get("show_common_only", True)
    items = df[df[column] == value].sort_values("Ingredient Name")

    for _, row in items.iterrows():
        item_name = row["Ingredient Name"]
        key = f"inv_{is_owner}_{column}_{value}_{item_name}"
        is_common = row["Common"] == "Yes"

        if show_common_only and not is_common:
            already_on = st.session_state.get(key, row["On-Hand"] == "Yes")
            if already_on:
                selected_inventory.append(item_name)
            continue

        checked = st.toggle(
            item_name,
            value=(row["On-Hand"] == "Yes"),
            key=key,
        )
        if checked:
            selected_inventory.append(item_name)


def _render_tab_content(df, column, values, is_owner, selected_inventory):
    """Renders one tab's contents. A tab backed by multiple values (e.g.
    Wines' 4 Category values, or Spirits' 7 Family values) shows each as
    its own sub-header; a tab backed by a single value renders flat."""
    present = [v for v in values if not df[df[column] == v].empty]
    if len(present) <= 1:
        if present:
            _render_ingredient_toggles(df, column, present[0], is_owner, selected_inventory)
        return
    for value in present:
        st.markdown(f"**{value}**")
        _render_ingredient_toggles(df, column, value, is_owner, selected_inventory)


def _render_category_group(df, tab_map, is_owner, selected_inventory):
    """Renders one parent group's contents inside whatever container is
    currently open (an expander). Uses one Streamlit tab per entry in
    tab_map, skipping any tab with no present data, and collapses to a
    flat layout (no tabs) if only one tab ends up with data."""
    present_tabs = {
        label: spec for label, spec in tab_map.items()
        if any(not df[df[spec["column"]] == v].empty for v in spec["values"])
    }
    if not present_tabs:
        return
    if len(present_tabs) == 1:
        spec = next(iter(present_tabs.values()))
        _render_tab_content(df, spec["column"], spec["values"], is_owner, selected_inventory)
        return
    tabs = st.tabs(list(present_tabs.keys()))
    for tab, spec in zip(tabs, present_tabs.values()):
        with tab:
            _render_tab_content(df, spec["column"], spec["values"], is_owner, selected_inventory)

def _get_cocktail_metadata(cocktail_id, cocktails_df, cocktail_recipes_df):
    """Looks up display metadata for a Tried/Untried cocktail from the
    sheet data. Returns None for New cocktails (cocktail_id is null) or
    if the id doesn't match anything in the sheet -- callers should
    treat a None return as "no sheet-backed stats to show"."""
    if not cocktail_id:
        return None

    match = cocktails_df[cocktails_df["Cocktail ID"] == cocktail_id]
    if match.empty:
        return None
    row = match.iloc[0]

    recipe_lines = cocktail_recipes_df[cocktail_recipes_df["Cocktail ID"] == cocktail_id]
    cost_per_serving = pd.to_numeric(recipe_lines["Cost"], errors="coerce").sum()
    standard_drinks = pd.to_numeric(recipe_lines["Standard Drinks"], errors="coerce").sum()

    return {
        "tried": row["Tried"],
        "rating": row["Rating"],
        "glassware": row["Glassware"],
        "prep_method": row["Prep Method"],
        "cost_per_serving": cost_per_serving,
        "standard_drinks": standard_drinks,
    }


def _rating_value(cocktail):
    """Best-effort numeric Rating, defaulting to 0 for blank/non-numeric
    values so sorting never blows up on cocktails that haven't been
    rated yet."""
    try:
        return float(cocktail["Rating"])
    except (TypeError, ValueError):
        return 0.0


def _try_algorithmic_bypass(params, cocktails_df, cocktail_recipes_df):
    """
    Skips the LLM entirely for the one case where it adds nothing: an
    existing recipe (Tried or Untried) under Mode A ("only show me
    recipes where I have exactly everything"). That's a pure filter --
    every ingredient line either is or isn't in selected_inventory, no
    substitution reasoning or invention required -- so it's computed
    directly from the sheet instead of paying for an API call.

    Returns None if this request doesn't qualify (New recipes, or any
    missing-ingredient mode other than Mode A) -- the caller should fall
    through to the LLM in that case. Returns a list (possibly empty, if
    nothing matches) in every other case, matching generate_cocktail_plan's
    output schema exactly so the results UI doesn't need to know which
    path produced them.
    """
    if params["recipe_source"] == "New recipes":
        return None
    if params["missing_ingredient_handling"] != "Only show me recipes where I have exactly everything":
        return None

    on_hand = set(params["selected_inventory"])
    want_tried = params["recipe_source"] == "Tried recipes"

    candidates = cocktails_df[
        cocktails_df["Tried"] == "Yes" if want_tried else cocktails_df["Tried"] != "Yes"
    ]

    matches = []
    for _, cocktail in candidates.iterrows():
        recipe_lines = cocktail_recipes_df[
            cocktail_recipes_df["Cocktail ID"] == cocktail["Cocktail ID"]
        ]
        if recipe_lines.empty:
            continue
        needed = set(recipe_lines["Ingredient Name"])
        if not needed.issubset(on_hand):
            continue
        matches.append((cocktail, recipe_lines))

    if not matches:
        return []

    # Favor higher-rated drinks in Tried mode without making it fully
    # deterministic: sort into a pool by rating, then shuffle within it,
    # so re-clicking Get Recommendations still surfaces some variety
    # instead of the exact same top N every time.
    if want_tried:
        matches.sort(key=lambda pair: _rating_value(pair[0]), reverse=True)
        pool = matches[: max(params["num_drinks"] * 2, len(matches))]
    else:
        pool = list(matches)

    random.shuffle(pool)
    chosen = pool[: params["num_drinks"]]

    cocktails_out = []
    for cocktail, recipe_lines in chosen:
        ingredients = [
            {
                "item": line["Ingredient Name"],
                "amount": f"{line['Amount']} {line['Drink Unit']}".strip(),
                "on_hand": True,
            }
            for _, line in recipe_lines.iterrows()
        ]

        if want_tried:
            why = "One of your favorites — you already have everything it calls for."
        else:
            why = "Already in your recipe list, and you have everything on hand to make it."

        batch_note = cocktail["Batch Note"] if cocktail["Batch Note"] else (
            "Scales easily for a group." if cocktail["Batch Friendly"] == "Yes"
            else "Best made to order, one at a time."
        )

        cocktails_out.append({
            "name": cocktail["Cocktail Name"],
            "source": "tried" if want_tried else "untried",
            "cocktail_id": cocktail["Cocktail ID"],
            "why": why,
            "ingredients": ingredients,
            "effort": cocktail["Effort"] if cocktail["Effort"] else "Moderate",
            "batch_note": batch_note,
        })

    return cocktails_out


def _render_my_bar_tab(cocktails_df, cocktail_recipes_df, cocktail_ingredients_df, is_owner):
    """Browsable view over the full Cocktails sheet -- every recipe in
    the database, tried or not, independent of on-hand inventory or any
    generated plan. Search/filter/sort only; no LLM involved."""
    st.caption("Everything in your cocktail database, searchable and browsable.")
    if not is_owner:
        st.caption("Tried status and ratings reflect the host's history, not yours.")

    search_cols = st.columns(2)
    with search_cols[0]:
        cocktail_names = sorted(n for n in cocktails_df["Cocktail Name"].unique() if n)
        name_search = st.selectbox(
            "Search by name", ["Any"] + cocktail_names
        )
    with search_cols[1]:
        ingredient_names = sorted(
            n for n in cocktail_ingredients_df["Ingredient Name"].unique() if n
        )
        ingredient_search = st.selectbox(
            "Search by ingredient", ["Any"] + ingredient_names
        )

    filter_cols = st.columns(3)
    with filter_cols[0]:
        tried_filter = st.selectbox("Status", ["All", "Tried only", "Untried only"])
    with filter_cols[1]:
        categories = sorted(c for c in cocktails_df["Category"].unique() if c)
        category_filter = st.multiselect("Category", categories)
    with filter_cols[2]:
        sort_by = st.selectbox("Sort by", ["Name", "Rating (high to low)"])

    df = cocktails_df.copy()
    if name_search != "Any":
        df = df[df["Cocktail Name"] == name_search]
    if ingredient_search != "Any":
        matching_ids = cocktail_recipes_df[
            cocktail_recipes_df["Ingredient Name"] == ingredient_search
        ]["Cocktail ID"].unique()
        df = df[df["Cocktail ID"].isin(matching_ids)]
    if tried_filter == "Tried only":
        df = df[df["Tried"] == "Yes"]
    elif tried_filter == "Untried only":
        df = df[df["Tried"] != "Yes"]
    if category_filter:
        df = df[df["Category"].isin(category_filter)]

    if sort_by == "Rating (high to low)":
        df = df.assign(_r=pd.to_numeric(df["Rating"], errors="coerce")).sort_values(
            "_r", ascending=False, na_position="last"
        )
    else:
        df = df.sort_values("Cocktail Name")

    st.caption(f"{len(df)} cocktail{'s' if len(df) != 1 else ''}")
    if df.empty:
        st.info("No cocktails match those filters.")
        return

    def _render_my_bar_card(cocktail):
        badges = [p for p in [cocktail["Category"], cocktail["Base Spirit"]] if p]

        if cocktail["Tried"] == "Yes":
            rating = cocktail["Rating"]
            rating_str = f" ({rating}/5)" if pd.notna(rating) and rating != "" else ""
            status = f"⭐ Tried{rating_str}"
        else:
            status = "Untried"

        recipe_lines = cocktail_recipes_df[
            cocktail_recipes_df["Cocktail ID"] == cocktail["Cocktail ID"]
        ]
        expander_lines = []
        if cocktail["Glassware"]:
            expander_lines.append(f"Glass: {cocktail['Glassware']}")
        if cocktail["Prep Method"]:
            expander_lines.append(f"Prep: {cocktail['Prep Method']}")
        for _, line in recipe_lines.iterrows():
            expander_lines.append(f"- {line['Amount']} {line['Drink Unit']} {line['Ingredient Name']}")
        if cocktail["Effort"]:
            expander_lines.append(f"Effort: {cocktail['Effort']}")
        if cocktail["Batch Note"]:
            expander_lines.append(f"Batching: {cocktail['Batch Note']}")

        render_metadata_card(
            cocktail["Cocktail Name"],
            badges=badges,
            body=status,
            footer=cocktail["Notes"] if cocktail["Notes"] and is_owner else None,
            expander=("Recipe", expander_lines),
        )

    NUM_COLUMNS = 3
    columns = st.columns(NUM_COLUMNS)
    for i, (_, cocktail) in enumerate(df.iterrows()):
        with columns[i % NUM_COLUMNS]:
            _render_my_bar_card(cocktail)


def render_cocktail_planner_page():
    page_header("Cocktail Planner", "Get personalized cocktail recommendations from your own bar")

    # Matches the flag set in app.py's Owner Access expander.
    is_owner = st.session_state.get("owner_unlocked", False)
    workbook = load_cocktail_workbook(is_owner)
    cocktail_ingredients_df = workbook["cocktail_ingredients"]

    if is_owner:
        st.info("🔓 Owner mode — inventory below reflects your real, persisted bar stock.")
    else:
        st.info("👋 Guest mode — inventory below starts from common defaults; toggle it to match what you actually have on hand.")

    my_bar_label = "My Bar" if is_owner else "Host's Bar"
    plan_tab, my_bar_tab = st.tabs(["Plan a Drink", my_bar_label])

    with plan_tab:
        _render_plan_tab(workbook, cocktail_ingredients_df, is_owner)

    with my_bar_tab:
        _render_my_bar_tab(
            workbook["cocktails"], workbook["cocktail_recipes"], cocktail_ingredients_df, is_owner
        )


def _render_plan_tab(workbook, cocktail_ingredients_df, is_owner):

    with st.sidebar:
        sidebar_page_header("① Cocktail Plan Settings")

        sidebar_section("Recipe Source")
        recipe_source = st.radio(
            "Tried, untried, or something new?",
            options=["Tried recipes", "Untried recipes", "New recipes"]
        )
        if not is_owner:
            st.caption("Tried status and ratings reflect the host's history, not yours.")

        sidebar_section("Missing Ingredients")
        missing_ingredient_handling = st.radio(
            "How should we handle ingredients you don't have?",
            options=[
                "Only show me recipes where I have exactly everything",
                "I'm ok with using substitutes I have on-hand",
                "Show me recipes even if I'm missing ingredients — I'll shop later",
            ],
        )

        is_instant = (
            recipe_source != "New recipes"
            and missing_ingredient_handling == "Only show me recipes where I have exactly everything"
        )
        if is_instant:
            st.caption("⚡ Instant — pulled straight from your recipe list, no AI needed.")
        else:
            st.caption("🤖 Uses AI — requires your OpenAI API key.")

        sidebar_section("Party & Servings")
        party_size = st.radio(
            "How many people?",
            options=["1", "2-4", "5+"],
            horizontal=True,
        )

        num_drinks = st.number_input(
            "How many drinks to suggest?",
            min_value=1,
            max_value=20,
            value=3,
        )

        sidebar_section("Vibe")
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

    # Explicit roadmap: this page shows a lot before the primary button
    # (sidebar prefs + a large inventory grid), so state the path
    # instead of relying on layout alone to imply it. Full gating
    # (hiding inventory until some prior step is "done") isn't a good
    # fit here since the button itself depends on the inventory
    # selections -- there's nothing to gate them behind.
    st.caption("**① Preferences** in the sidebar → **② What's in your bar** below → **③ Get Recommendations**")

    # Inventory lives on the main page body, not the sidebar — too many
    # toggles to be usable squeezed into a narrow column.
    st.subheader("② Current Inventory")
    st.caption("What do you have and want to drink right now?")
    st.checkbox(
        "Show common ingredients only",
        value=True,
        key="show_common_only",
        help="Uncheck to reveal specialty/niche ingredients within each section.",
    )

    selected_inventory = []
    NUM_COLUMNS = 3
    columns = st.columns(NUM_COLUMNS)
    for i, (group_name, tab_map) in enumerate(CATEGORY_GROUPS.items()):
        with columns[i % NUM_COLUMNS]:
            with st.expander(group_name):
                _render_category_group(
                    cocktail_ingredients_df, tab_map, is_owner, selected_inventory
                )

    # Safety net: any sheet category not yet mapped into a parent group
    # still needs to show up somewhere rather than silently vanishing.
    mapped_categories = set()
    for tab_map in CATEGORY_GROUPS.values():
        for spec in tab_map.values():
            if spec["column"] == "Category":
                mapped_categories.update(spec["values"])
            elif spec["column"] == "Family":
                # Family is only ever populated for Spirit rows, so a
                # Family-keyed tab implicitly covers Category == "Spirit".
                mapped_categories.add("Spirit")
    unmapped_categories = sorted(
        set(cocktail_ingredients_df["Category"].unique()) - mapped_categories
    )
    if unmapped_categories:
        with st.expander("Other"):
            _render_tab_content(
                cocktail_ingredients_df, "Category", unmapped_categories, is_owner, selected_inventory
            )

    st.divider()

    situational_context = st.text_area(
        "Anything else? (occasion, mood, a bottle you're curious about, etc.)",
        placeholder="e.g. Curious about the Averna I bought last month...",
    )

    st.markdown("**③ Ready?**")
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
            "num_drinks": num_drinks,
            "drink_style": drink_style,
            "occasion": occasion,
            "selected_inventory": selected_inventory,
            "situational_context": situational_context,
        }

        # Mode A + an existing recipe is a pure lookup -- no reasoning or
        # invention needed -- so skip the LLM call entirely when it applies.
        bypass_result = _try_algorithmic_bypass(
            params, workbook["cocktails"], workbook["cocktail_recipes"]
        )

        if bypass_result is not None:
            cocktails = bypass_result
        else:
            cocktail_ingredients_records = workbook["cocktail_ingredients"].drop(
                columns=["On-Hand"]
            ).to_dict(orient="records")

            workbook_json = {
                "cocktails": workbook["cocktails"].to_dict(orient="records"),
                "cocktail_ingredients": cocktail_ingredients_records,
                "cocktail_recipes": workbook["cocktail_recipes"].to_dict(orient="records"),
            }

            cache_bust = st.session_state.get("cocktail_cache_bust", 0)
            st.session_state["cocktail_cache_bust"] = cache_bust + 1

            try:
                with st.spinner("Shaking up your recommendations..."):
                    cocktails = generate_cocktail_plan(
                        params, workbook_json, api_key, cache_bust=cache_bust
                    )
            except ValueError as e:
                st.error(str(e))
                cocktails = None

        response = {"cocktails": cocktails} if cocktails is not None else None

        if response and not response["cocktails"]:
            st.warning(
                "Nothing matches exactly what you have on hand right now. "
                "Try allowing substitutions, or add more to your inventory above."
            )
        elif response:
            st.subheader("Recommendations")

            # extra_lines_fn approximates badges (up to 5 for a
            # Tried/Untried cocktail: rating, glassware, method,
            # standard drinks, cost) + a footer line, plus one line per
            # ingredient (the biggest source of height variance --
            # a 3-ingredient drink and a 6-ingredient one previously
            # got the same estimate). base_px bumped again -- 150 was
            # still reading short once the ingredient list filled in.
            sizing = compute_card_height(
                response["cocktails"],
                title_fn=lambda c: c["name"],
                body_fn=lambda c: c["why"],
                extra_lines_fn=lambda c: len(c["ingredients"]) + 6,
                base_px=220,
            )

            RESULT_COLUMNS = 2
            columns = st.columns(RESULT_COLUMNS)
            for i, cocktail in enumerate(response["cocktails"]):
                with columns[i % RESULT_COLUMNS]:
                    # Tried/Untried only -- New cocktails have no
                    # cocktail_id and therefore no sheet-backed stats.
                    metadata = _get_cocktail_metadata(
                        cocktail.get("cocktail_id"),
                        workbook["cocktails"],
                        workbook["cocktail_recipes"],
                    )

                    badges = []

                    if metadata:
                        # Sheet-backed cocktails already show tried/rating
                        # status via the badge below -- the old "Tried
                        # recipe" badge duplicated it. That badge now only
                        # shows for New cocktails, which have no metadata.
                        if metadata["tried"] == "Yes":
                            rating = metadata["rating"]
                            if pd.notna(rating) and rating != "":
                                badges.append(f"⭐ **Rating:** {rating}/5")
                            else:
                                badges.append("⭐ **Tried** (not yet rated)")
                        else:
                            badges.append("Untried")
                        if metadata["glassware"]:
                            badges.append(("🍸 Glassware", str(metadata["glassware"])))
                        if metadata["prep_method"]:
                            badges.append(("🥄 Method", str(metadata["prep_method"])))

                        # Now part of the same attribute list as the rest
                        # of the badges above (same emoji+bold format),
                        # not a separate metrics row. Standard Drinks/Cost
                        # only exist for sheet-backed Tried/Untried
                        # cocktails, same as before.
                        if pd.notna(metadata["standard_drinks"]) and metadata["standard_drinks"] > 0:
                            badges.append(("🥂 Standard Drinks", f"{metadata['standard_drinks']:.1f}"))
                        if pd.notna(metadata["cost_per_serving"]) and metadata["cost_per_serving"] > 0:
                            badges.append(("💰 Cost/Serving", f"${metadata['cost_per_serving']:.2f}"))
                    else:
                        badges.append(f"{cocktail['source'].capitalize()} recipe")

                    ingredient_lines = []
                    for ing in cocktail["ingredients"]:
                        marker = "✅" if ing["on_hand"] else "🛒"
                        line = f"{marker} {ing['amount']} {ing['item']}"
                        if ing.get("note"):
                            line += f"  \n*{ing['note']}*"
                        ingredient_lines.append(line)

                    render_metadata_card(
                        cocktail["name"],
                        rank=i + 1,
                        height=sizing.height,
                        title_lines=sizing.title_lines,
                        badges=badges,
                        body=cocktail["why"],
                        list_items=ingredient_lines,
                        footer=f"Batch note: {cocktail['batch_note']}",
                    )

    else:
        st.info("Choose your inventory above, set preferences in the sidebar, and click **Get Recommendations**.")