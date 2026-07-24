import streamlit as st

SHEET_NAME = "Meal Plan for Web App"


def is_owner_mode() -> bool:
    """
    True when running with the owner's own secrets.toml (OWNER_MODE = true,
    for local/private use), OR when the current visitor has unlocked owner
    access for this session by entering the correct OWNER_PASSCODE (for a
    single public deployment shared with trusted people, e.g. family).
    """
    if bool(st.secrets.get("OWNER_MODE", False)):
        return True
    return bool(st.session_state.get("owner_unlocked", False))