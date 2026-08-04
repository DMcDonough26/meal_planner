import streamlit as st
import pandas as pd
import textwrap
from typing import NamedTuple

from config.constants import is_owner_mode
from services.llm_client import APPROVED_CHEFS, DEFAULT_APPROVED_CHEFS


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
    """Section header for a sidebar control group. The divider goes
    BEFORE the title, not after -- it separates this section from
    whatever trailed the previous one (often a caption), instead of
    wedging itself between the header and its own widgets, which was
    the actual cause of captions looking glued to the next title."""
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"#### {title}")


def sidebar_page_header(title: str):
    """One top-level heading per page's sidebar, rendered once before
    any sidebar_section() groups, so every page's control panel starts
    at the same visual weight. Previously 3 of 4 pages had one and
    Meal Planner's sidebar jumped straight into a subsection header
    with nothing above it."""
    st.sidebar.header(title)

def planning_controls(meals_df: pd.DataFrame, store_layout_df):

    sidebar_page_header("Meal Plan Settings")
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

    # -----------------------------
    # Section: Cooking Days
    # -----------------------------
    sidebar_section("Cooking Days")

    ALL_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    cook_days = st.sidebar.multiselect(
        "Which days do you want to cook?",
        ALL_WEEKDAYS,
        default=ALL_WEEKDAYS,
    )

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

    # -----------------------------
    # Section: Preferences
    # -----------------------------
    sidebar_section("Preferences")

    cuisine = st.sidebar.multiselect(
        "Cuisine preferences",
        ["Any"] + sorted(meals_df["Cuisine"].dropna().unique()),
        default=["Any"]
    )


    # -----------------------------
    # Section: Notes
    # -----------------------------
    sidebar_section("Notes / Constraints")

    notes = st.sidebar.text_area(
        "Notes (optional)",
        placeholder="e.g., avoid spicy, use up chicken thighs, guests on Thursday..."
    )

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
        "cook_days": cook_days,
        "total_meals": total_meals,
        "total_servings_consumed": total_servings_consumed,
        "total_servings_needed": total_servings_needed,
        "plan_date": plan_date
    }

def takeout_controls(meals_df):
    sidebar_page_header("Takeout Preferences")

    sidebar_section("Search Basics")

    location_anchor = st.sidebar.text_input(
        "Location (for distance estimates)",
        value="West County Center, St. Louis"
    )


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

def _estimate_wrapped_lines(text, chars_per_line=38):
    """Rough estimate of how many lines `text` will wrap to inside a
    card at typical card width/font size. Not pixel-exact -- just
    consistent enough to size a shared card height across a batch."""
    if not text:
        return 1
    return max(1, len(textwrap.wrap(str(text), chars_per_line)))


# Rough per-line pixel costs used by the card-height helpers below --
# title text renders larger (h3) than body/badge/metric text, so it
# gets its own constant. TITLE_CHARS_PER_LINE is the matching wrap-
# width assumption, shared between compute_card_height() (which sizes
# a batch) and render_metadata_card() (which pads each card's title
# to that size) so the two stay in sync.
TITLE_PX_PER_LINE = 34
BODY_PX_PER_LINE = 22
TITLE_CHARS_PER_LINE = 22


class CardSizing(NamedTuple):
    """Returned by compute_card_height(). `height` goes to
    render_metadata_card(height=...); `title_lines` goes to
    render_metadata_card(title_lines=...) so the title area reserves
    the same vertical space on every card in the batch and body text
    starts at the same height regardless of how long any one card's
    title happens to be."""
    height: int
    title_lines: int


def compute_card_height(
    items,
    title_fn,
    body_fn,
    extra_lines_fn=None,
    base_px=110,
    px_per_line=BODY_PX_PER_LINE,
    chars_per_line=38,
    title_chars_per_line=TITLE_CHARS_PER_LINE,
):
    """
    Computes a shared CardSizing(height, title_lines) for a batch of
    cards, sized to the longest title, longest body text, and (via
    extra_lines_fn) whatever fixed-line content -- badges, metrics,
    footer -- the batch's busiest card needs. Pass sizing.height as
    height= and sizing.title_lines as title_lines= to every
    render_metadata_card() call in the batch, so cards line up instead
    of varying with reasoning-note, name, or attribute-list length.

    title_fn/body_fn extract the relevant text from each item.
    extra_lines_fn(item), if given, returns the number of additional
    non-wrapping lines that item's card renders below the body (e.g.
    len(badges) + 1 for a metrics line + 1 for a footer line) -- an
    estimate is fine, this doesn't need to be exact.
    """
    if not items:
        return CardSizing(base_px + TITLE_PX_PER_LINE, 1)

    title_lines = [_estimate_wrapped_lines(title_fn(i), title_chars_per_line) for i in items]
    body_lines = [_estimate_wrapped_lines(body_fn(i), chars_per_line) for i in items]
    extra_lines = [(extra_lines_fn(i) if extra_lines_fn else 0) for i in items]

    max_title_lines = max(title_lines)
    max_body_lines = max(body_lines)
    max_extra_lines = max(extra_lines)

    height = (
        base_px
        + max_title_lines * TITLE_PX_PER_LINE
        + (max_body_lines + max_extra_lines) * px_per_line
    )
    return CardSizing(height=height, title_lines=max_title_lines)


def compute_day_card_height(days, slot_text_fn, base_px=90, px_per_line=BODY_PX_PER_LINE, chars_per_line=34):
    """Sibling of compute_card_height() for the Meal Plan tab's day
    cards, which don't have a single title+body but a variable number
    of meal-slot lines instead. `days` is a list of per-day slot lists;
    slot_text_fn(slot) returns that slot's rendered line so its wrap
    length can be estimated. Sized to whichever day has the most total
    wrapped lines across its slots, so every day's card -- even ones
    with fewer or shorter meal names -- ends up the same height."""
    if not days:
        return base_px
    max_lines = max(
        sum(_estimate_wrapped_lines(slot_text_fn(slot), chars_per_line) for slot in day_slots)
        for day_slots in days
    )
    return base_px + max_lines * px_per_line


def render_metadata_card(
    title: str,
    badges=None,
    metrics=None,
    body: str | None = None,
    list_items=None,
    footer: str | None = None,
    expander=None,
    rank: int | None = None,
    height: int | None = None,
    title_lines: int | None = None,
    top_link: str | None = None,
    badges_position: str = "bottom",
):
    """
    Shared card shell for every recommendation surface in the app --
    Plan's Recipes tab, Takeout, Recipe Ideas, and both Cocktail tabs.

    Render order: title -> [badges if badges_position="top"] -> top_link
    -> body -> list_items -> [badges if badges_position="bottom"] ->
    metrics -> footer -> expander.

    badges: short categorical facts (Cuisine, Effort, Glassware, etc.)
      -- each entry either a plain string, or a (label, value) tuple
      rendered as "**label:** value" for facts that read better
      labeled. One per line, at normal text size (this is the card's
      main attribute list, not fine print).
    metrics: list of (label, value) tuples -- rendered at that same
      normal text size, as one line ("**label:** value · **label:**
      value...").
    body: a free paragraph -- Reasoning, Blurb, or Why. Rendered right
      after the title (and top_link, if given).
    list_items: optional bullet list right after the body (e.g. an
      ingredients list) under an "Ingredients" label.
    footer: trailing caption (e.g. a batch note) -- stays smallest,
      at the very bottom of the card.
    expander: optional (label, lines) tuple rendered as an st.expander
      inside the card, for details that don't need to be visible by
      default (e.g. a full cocktail recipe).
    rank: 1-based position in a ranked list (e.g. 1 for the top pick).
      Rendered as "#1." before the title. Omit for cards that aren't a
      ranked recommendation (e.g. My Bar's browsable catalog, or a
      calendar day card).
    height: fixed card height in px (see compute_card_height()). When
      set, the card becomes a fixed-height container so every card in
      a batch lines up regardless of content length; overflow content
      scrolls inside the card rather than stretching it.
    title_lines: batch's longest title, in estimated wrapped lines (see
      compute_card_height()) -- pads shorter titles with blank spacer
      lines so body text starts at roughly the same height across the
      batch. Never truncates a longer title (unlike an earlier version
      of this that used a fixed-height sub-container, which could clip
      a title that ran long) -- it only ever adds space, never removes
      it. Only meaningful alongside height.
    top_link: optional ready-made markdown link (e.g.
      "[View recipe](https://...)"), rendered directly under the
      title/badges, before the body -- for cards where the reference
      link belongs above the reasoning rather than buried in the
      footer.
    badges_position: "bottom" (default) renders badges after body/
      list_items, as the card's attribute section. "top" renders them
      right after the title instead (before top_link/body) -- for
      cards where a badge (e.g. a chef byline) reads better as part of
      the header than as trailing metadata.
    """
    def _format_badge(badge):
        if isinstance(badge, tuple):
            label, value = badge
            return f"**{label}:** {value}"
        return str(badge)

    def _render_badges():
        if badges:
            st.markdown("  \n".join(_format_badge(b) for b in badges))

    with st.container(border=True, **({"height": height} if height is not None else {})):
        display_title = f"### #{rank}. {title}" if rank else f"### {title}"
        st.markdown(display_title)

        if title_lines:
            # Pads shorter titles with blank spacer lines (at body
            # line-height) so body text starts at roughly the same
            # vertical position across the batch, without ever
            # constraining/clipping the title itself the way a
            # fixed-height container would. Rendered as ONE markdown
            # call with soft line breaks -- separate st.markdown()
            # calls per line each carry their own element spacing in
            # Streamlit, which compounds unpredictably and was why
            # this wasn't lining up titles of different wrapped
            # lengths.
            # Whole-body-line filler units proved too coarse to land
            # precisely. Rendering at caption size (shorter line-height
            # than body text) gives a finer unit, and TITLE_FILLER_SCALE
            # below is the dial to fine-tune it further -- currently
            # overshooting by ~half a caption-line at scale=1.0, so try
            # something like 0.7-0.8 next.
            TITLE_FILLER_SCALE = 1.0
            actual_title_lines = _estimate_wrapped_lines(title, TITLE_CHARS_PER_LINE)
            filler_lines = round(max(0, title_lines - actual_title_lines) * TITLE_FILLER_SCALE)
            if filler_lines:
                st.caption("  \n".join(["&nbsp;"] * filler_lines))

        if badges_position == "top":
            _render_badges()

        if top_link:
            st.markdown(top_link)

        if body:
            st.write(body)

        if list_items:
            st.markdown("**Ingredients**")
            for item in list_items:
                st.write(item)

        if badges_position == "bottom":
            _render_badges()

        if metrics:
            st.markdown(" · ".join(f"**{label}:** {value}" for label, value in metrics))

        if footer:
            st.caption(footer)

        if expander:
            label, lines = expander
            with st.expander(label):
                for line in lines:
                    st.write(line)

def render_day_plan_card(day_name: str, slots, height: int | None = None):
    """
    Card for one day of the Meal Plan tab's weekly view. Each row is
    one meal slot on a single line (icon + slot name + meal name).
    Category is deliberately not shown -- the meal name is more useful
    in that spot. The "Day N" caption is also dropped -- day_name
    (e.g. "Monday") already identifies the card without it.

    slots: list of dicts with keys "icon", "slot", "meal_name".
    height: fixed card height in px (see compute_day_card_height()),
      so every day's card is the same size regardless of how many
      slots it has or how long its meal names run.
    """
    with st.container(border=True, **({"height": height} if height is not None else {})):
        st.markdown(f"### {day_name}")

        for slot in slots:
            st.markdown(f"**{slot['icon']} {slot['slot']}:** {slot['meal_name']}")


def render_card_grid(items, render_fn, num_columns: int = 3):
    """Lays out a list of items in a fixed-column grid, wrapping to a
    new row automatically -- the grid layout now shared by Plan's
    Recipes tab and Takeout. render_fn(item, rank) is called once per
    item, inside its own column, where rank is the item's 1-based
    position in `items` -- callers that want ranking numbers on their
    cards just forward it to render_metadata_card(rank=...); callers
    that don't (e.g. calendar day cards) accept and ignore it. Recipe
    Ideas and Cocktail keep their own manual st.columns() loops since
    each has extra per-item logic (an "Add to cookbook" button, a
    metadata lookup) that doesn't fit a generic render_fn(item, rank)
    signature cleanly."""
    columns = st.columns(num_columns)
    for i, item in enumerate(items):
        with columns[i % num_columns]:
            render_fn(item, i + 1)

def recipe_ideas_controls(meals_df):
    """
    Sidebar controls for the Recipe Ideas page. Deliberately lighter than
    planning_controls -- this mode doesn't need days/servings/bulk-cook
    params, since ideas aren't scaled or turned into a grocery list.
    """
    sidebar_page_header("Recipe Idea Preferences")

    sidebar_section("Preferences")

    cuisines = st.sidebar.multiselect(
        "Cuisines you're interested in",
        sorted(meals_df["Cuisine"].dropna().unique().tolist())
    )

    num_ideas = st.sidebar.number_input(
        "How many ideas?",
        min_value=1,
        max_value=10,
        value=3
    )

    sidebar_section("Chefs to Suggest From")

    chefs = st.sidebar.multiselect(
        "Which chefs should ideas come from?",
        APPROVED_CHEFS,
        default=DEFAULT_APPROVED_CHEFS,
    )

    # One free-form field instead of two -- previously this page had a
    # separate "Ingredients you'd like to use" box alongside this one,
    # which was redundant. Its intent (ingredients to use up) is now
    # just part of what this field's placeholder invites.
    sidebar_section("Notes")

    notes = st.sidebar.text_area(
        "Anything else? (optional)",
        placeholder=(
            "e.g. nothing too spicy, quick weeknight options, vegetarian, "
            "ingredients you'd like to use up..."
        )
    )

    generate = st.sidebar.button("Suggest Recipe Ideas")

    if generate and not chefs:
        st.sidebar.warning("Select at least one chef before generating ideas.")
        generate = False

    return {
        "cuisines": cuisines,
        "chefs": chefs,
        # Kept as an empty string, not removed, so generate_recipe_ideas()
        # (services/llm_client.py) doesn't KeyError if its prompt-building
        # code still reads params["ingredients_on_hand"] -- that file
        # wasn't part of this pass, so it may still expect the key. Worth
        # checking whether its "ingredients to use up" prompting should
        # now pull from `notes` instead.
        "ingredients_on_hand": "",
        "num_ideas": num_ideas,
        "notes": notes,
        "generate": generate
    }