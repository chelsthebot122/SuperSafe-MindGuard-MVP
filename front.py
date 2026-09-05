"""
MindGuard Portal — Local PII Anonymization Engine
Requires streamlit >= 1.34 (uses st.container(key=...) for scoped CSS targeting,
which is what fixes the stray/misaligned block that used to render above the
header — see comments below for why).
"""

import streamlit as st
import pandas as pd

from backend.redactor import redact_text, get_engines
from backend.pri import calculate_pri_reduction, calculate_csv_pri_reduction
from backend.csv_scrubber import process_health_csv, MAX_UPLOAD_SIZE_MB, MAX_UPLOAD_SIZE_BYTES

# ------------------------------------------------------------------
# Page Configuration
# ------------------------------------------------------------------
st.set_page_config(
    page_title="MindGuard Portal",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ------------------------------------------------------------------
# Session State
# ------------------------------------------------------------------
if "page" not in st.session_state:
    st.session_state.page = "Home"

if "theme" not in st.session_state:
    st.session_state.theme = "Light"

# Consent gate state. This is intentionally stored in st.session_state
# rather than a real browser cookie/localStorage — Streamlit's
# session_state IS the "local session storage" the spec asks the cookie
# banner to request permission for (it's exactly where the theme
# preference already lives). The honest tradeoff: it only lasts for
# this browser tab's session, not across a hard refresh or new visit —
# there is no real persistent-across-sessions storage without adding an
# external browser-storage component, which is out of scope for the MVP.
if "consent_given" not in st.session_state:
    st.session_state.consent_given = False

if "show_terms_review" not in st.session_state:
    st.session_state.show_terms_review = False

# Text size preference — a plain multiplier applied to every font-size
# in the CSS below via the fs() helper. Added because font size is
# genuinely subjective (what looks fine to one person can be too small
# for another), so it's a real setting rather than something baked in.
if "font_scale" not in st.session_state:
    st.session_state.font_scale = 1.0

FONT_SIZE_STEPS = [
    ("S", 1.0, "font_size_btn_normal"),
    ("M", 1.15, "font_size_btn_large"),
    ("L", 1.5, "font_size_btn_xlarge"),
]
active_font_key = next(
    key for _, scale, key in FONT_SIZE_STEPS if scale == st.session_state.font_scale
)


def fs(px: float) -> str:
    """Scale a base px value by the current text-size setting."""
    return f"{round(px * st.session_state.font_scale, 2)}px"


def set_page(page_name):
    st.session_state.page = page_name


def toggle_theme(mode):
    st.session_state.theme = mode


# ------------------------------------------------------------------
# Design Tokens
# ------------------------------------------------------------------
# Dark: near-black navy with a teal "shield" accent (security/scan feel,
# deliberately not the default warm-cream/terracotta look).
# Light: cool slate-white, same teal accent darkened for contrast.
if st.session_state.theme == "Dark":
    bg_app = "#0A0E17"
    bg_nav = "#121826"
    bg_card = "#121826"
    bg_card_alt = "#171F30"
    text_main = "#E9ECF4"
    text_sub = "#8B93A8"
    border_color = "#232B3D"
    input_bg = "#0D1220"
    accent = "#20BFAC"          # teal — brand / primary actions (dialed back from neon)
    accent_txt_on = "#01130F"   # near-black for max contrast on the bright accent
    danger_bg = "#4A1526"
    danger_txt = "#FF6B81"
    danger_border = "#7A2440"
    safe_bg = "#0E2A22"
    safe_txt = "#34D399"
    safe_border = "#155E4A"
    info_bg = "#0E2430"
    info_txt = "#67E8F9"
    info_border = "#164C5E"
    toggle_track = "#1B2333"
    select_bg = "#1B2333"
    shadow = "0 4px 16px rgba(0, 0, 0, 0.35)"
else:  # Light
    bg_app = "#F4F6FA"
    bg_nav = "#FFFFFF"
    bg_card = "#FFFFFF"
    bg_card_alt = "#F7F9FC"
    text_main = "#0F1729"
    text_sub = "#5B6478"
    border_color = "#DCE2ED"
    input_bg = "#FFFFFF"
    accent = "#0D9488"          # teal-700 — darker for AA contrast on white
    accent_txt_on = "#FFFFFF"
    danger_bg = "#FFF1F2"
    danger_txt = "#BE123C"
    danger_border = "#FECDD3"
    safe_bg = "#ECFDF5"
    safe_txt = "#047857"
    safe_border = "#A7F3D0"
    info_bg = "#ECFEFF"
    info_txt = "#0E7490"
    info_border = "#A5F3FC"
    toggle_track = "#E7EBF3"
    select_bg = "#D6EFEC"
    shadow = "0 4px 16px rgba(15, 23, 41, 0.06)"

active_theme_key = "theme_light_btn" if st.session_state.theme == "Light" else "theme_dark_btn"

FONT_DISPLAY = "'Space Grotesk', 'Segoe UI', sans-serif"
FONT_BODY = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
FONT_MONO = "'IBM Plex Mono', 'SFMono-Regular', Consolas, monospace"

# ------------------------------------------------------------------
# Global CSS
# ------------------------------------------------------------------
st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap');

    .stApp {{
        background-color: {bg_app} !important;
    }}

    html, body, [class*="css"] {{
        font-family: {FONT_BODY} !important;
    }}

    h1, h2, h3, h4, h5, h6 {{
        font-family: {FONT_BODY} !important;
        color: {text_main} !important;
        letter-spacing: -0.01em;
    }}

    p, span, label, div {{
        color: {text_main};
        font-family: {FONT_BODY};
        font-size:{fs(16.5)};
    }}

    /* Streamlit wraps button labels in a nested <p>, which was matching
       the generic rule above and silently overriding whatever text
       color we set on the button itself — that's what made text on the
       teal buttons render as near-white instead of the dark, readable
       color set below. Forcing every button's descendants to inherit
       fixes it everywhere at once. */
    .stButton > button * {{
        color: inherit !important;
    }}

    /* Kill Streamlit's default top padding so the header sits flush */
    .block-container {{
        padding-top: 2rem !important;
        max-width: 1180px !important;
    }}

    /* ---------------- Header ----------------
       Scoped to this container via st.container(key="app_header") so the
       CSS applies to an element Streamlit actually renders as a real
       parent — this is what fixes the stray empty block that used to
       appear above the title (that happened because a raw
       st.markdown('<div>...') was never truly wrapping the st.columns()
       that followed it; they're separate DOM siblings, not parent/child,
       so the open <div> rendered as its own empty box). */
    .st-key-app_header {{
        background-color: {bg_nav};
        border: 1px solid {border_color};
        border-radius: 14px;
        padding: 18px 26px;
        box-shadow: {shadow};
        margin-bottom: 28px;
    }}

    .st-key-app_header [data-testid="stHorizontalBlock"] {{
        align-items: center;
    }}

    /* ---------------- Text size segmented control ----------------
       Deliberately real buttons, not a native selectbox — three
       separate CSS strategies for styling the native dropdown's OPEN
       option list (data-testid, data-baseweb attributes, then ARIA
       roles) all had zero effect, which points to the popover
       rendering inside a Shadow DOM boundary: a browser feature that
       makes a component's internals genuinely unreachable by external
       page CSS, by design — not just hard to target. Buttons sitting
       in our own scoped containers sidestep that entirely; there's no
       portal and no Shadow DOM involved, so they're guaranteed
       stylable.

       Labels are "S"/"M"/"L" rather than a font-size preview on the
       button itself — relying on subtle rendered font-size differences
       to communicate meaning wasn't reading clearly at this compact a
       size, so the letters carry the meaning directly instead. Kept
       intentionally small and compact (not growing with font_scale, and
       not part of the header's own scaling) so this control can never
       collide with anything next to it, at any text-size setting. */
    .st-key-font_size_toggle {{
        background-color: {toggle_track};
        border-radius: 10px;
        padding: 4px;
        display: flex;
        align-items: center;
        gap: 3px;
    }}
    .st-key-font_size_toggle [data-testid="stHorizontalBlock"] {{
        gap: 3px;
        align-items: center !important;
    }}
    .st-key-font_size_toggle .stButton > button {{
        border: none !important;
        border-radius: 7px !important;
        background-color: transparent !important;
        color: {text_sub} !important;
        font-weight: 700 !important;
        box-shadow: none !important;
        line-height: 1 !important;
        font-size: 14px !important;
        padding: 7px 12px !important;
        min-width: 0 !important;
    }}
    .st-key-font_size_toggle .stButton > button:hover {{
        color: {text_main} !important;
    }}
    /* Whichever step is active gets the solid accent fill — same
       pattern as the theme toggle, computed each run from
       st.session_state.font_scale. */
    .st-key-{active_font_key} .stButton > button {{
        background-color: {accent} !important;
        color: {accent_txt_on} !important;
    }}
    .st-key-{active_font_key} .stButton > button:hover {{
        color: {accent_txt_on} !important;
    }}

    /* ---------------- Segmented theme toggle ---------------- */
    .st-key-theme_toggle {{
        background-color: {toggle_track};
        border-radius: 10px;
        padding: 4px;
        display: flex;
        gap: 2px;
    }}
    .st-key-theme_toggle [data-testid="stHorizontalBlock"] {{
        gap: 2px;
    }}
    .st-key-theme_toggle .stButton > button {{
        border: none !important;
        border-radius: 7px !important;
        background-color: transparent !important;
        color: {text_sub} !important;
        font-weight: 600 !important;
        font-size:{fs(13.5)} !important;
        padding: 7px 0 !important;
        box-shadow: none !important;
    }}
    .st-key-theme_toggle .stButton > button:hover {{
        color: {text_main} !important;
    }}
    /* Whichever segment is active gets the solid accent fill. Which key
       that is depends on st.session_state.theme, computed below since
       this whole CSS block is rebuilt every run. */
    .st-key-{active_theme_key} .stButton > button {{
        background-color: {accent} !important;
        color: {accent_txt_on} !important;
    }}
    .st-key-{active_theme_key} .stButton > button:hover {{
        color: {accent_txt_on} !important;
    }}

    /* ---------------- Text areas ---------------- */
    .stTextArea textarea {{
        background-color: {input_bg} !important;
        color: {text_main} !important;
        -webkit-text-fill-color: {text_main} !important;
        border: 1.5px solid {border_color} !important;
        border-radius: 10px !important;
        font-family: {FONT_MONO} !important;
        font-size:{fs(17)} !important;
        line-height: 1.75 !important;
        padding: 16px !important;
    }}
    .stTextArea textarea:focus {{
        border-color: {accent} !important;
        box-shadow: 0 0 0 3px {accent}33 !important;
    }}
    .stTextArea textarea:disabled {{
        background-color: {input_bg} !important;
        color: {text_main} !important;
        -webkit-text-fill-color: {text_main} !important;
        opacity: 1 !important;
    }}
    .stTextArea label {{
        font-weight: 700 !important;
        font-size:{fs(16)} !important;
        color: {text_sub} !important;
    }}

    /* ---------------- Inline code / mono badges ---------------- */
    code {{
        font-family: {FONT_MONO} !important;
        background-color: {info_bg} !important;
        color: {info_txt} !important;
        border: 1px solid {info_border} !important;
        padding: 3px 9px !important;
        border-radius: 6px !important;
        font-size:{fs(14.5)} !important;
        font-weight: 600 !important;
    }}

    /* ---------------- File uploader ---------------- */
    [data-testid="stFileUploader"] {{
        background-color: {bg_card} !important;
        border: 2px dashed {accent} !important;
        border-radius: 14px !important;
        padding: 28px !important;
    }}
    [data-testid="stFileUploader"] * {{
        color: {text_main} !important;
        background-color: transparent !important;
    }}
    [data-testid="stFileUploader"] section {{
        background-color: transparent !important;
    }}

    /* ---------------- Tooltips (the "?" help icon popovers) ----------------
       Streamlit's tooltip popup has a FIXED dark background regardless
       of the app's own theme. The file uploader's broad "* {{ color:
       text_main }}" rule above (and similar rules elsewhere) was
       bleeding onto it — so in Light mode, text_main (dark navy) was
       landing on that fixed-dark tooltip background and disappearing
       entirely. Forcing a fixed light color here (not theme-
       conditional, since the tooltip background itself never changes
       with the app theme) fixes it in both modes. */
    [data-testid="stTooltipContent"] {{
        color: #F1F5F9 !important;
    }}
    [data-testid="stTooltipContent"] * {{
        color: #F1F5F9 !important;
    }}

    /* ---------------- Checkbox (consent gate) ----------------
       Previous attempt targeted [role="checkbox"], which apparently
       isn't how this Streamlit version's markup is structured, so it
       silently matched nothing. There's also a second likely cause:
       browsers often auto-style native form controls based on the
       SYSTEM's dark/light setting, completely independent of a page's
       own CSS — which would explain a checkbox staying visually black
       even though the rest of the page is correctly themed. Fixing
       both at once:
       1) `accent-color` is the standards-based CSS property made
          specifically for retinting native checkboxes/radios — it
          works directly on the real <input>, regardless of whatever
          wrapper markup Streamlit puts around it.
       2) `color-scheme` tells the browser which palette to render
          native controls in, so it follows OUR app's chosen theme
          instead of silently deferring to the OS setting. */
    [data-testid="stCheckbox"] {{
        color-scheme: {"light" if st.session_state.theme == "Light" else "dark"};
    }}
    [data-testid="stCheckbox"] input[type="checkbox"] {{
        accent-color: {accent} !important;
        width: 20px !important;
        height: 20px !important;
        cursor: pointer !important;
    }}

    /* ---------------- Default buttons ---------------- */
    .stButton > button {{
        background-color: {bg_card} !important;
        color: {text_main} !important;
        border: 1.5px solid {border_color} !important;
        border-radius: 9px !important;
        font-weight: 700 !important;
        font-size:{fs(16)} !important;
        padding: 11px 18px !important;
        transition: all 0.15s ease !important;
    }}
    .stButton > button:hover {{
        border-color: {accent} !important;
        color: {accent} !important;
    }}
    .stButton > button[kind="primary"] {{
        background-color: {accent} !important;
        color: {accent_txt_on} !important;
        border: none !important;
        font-weight: 800 !important;
    }}
    .stButton > button[kind="primary"]:hover {{
        filter: brightness(1.08);
    }}
    .stButton > button:disabled {{
        opacity: 0.45 !important;
        cursor: not-allowed !important;
    }}

    /* ---------------- Download buttons ----------------
       st.download_button renders in its OWN container
       ("stDownloadButton"), completely separate from the regular
       ".stButton" class every rule above targets — which is exactly
       why the Export Sanitized CSV button was getting none of this
       styling and just sat there in Streamlit's bare default look.
       Mirroring the same rules here (including the "* {{ color:
       inherit }}" fix for nested label text) makes it match every
       other primary button in the app. */
    [data-testid="stDownloadButton"] > button {{
        background-color: {accent} !important;
        color: {accent_txt_on} !important;
        border: none !important;
        border-radius: 9px !important;
        font-weight: 800 !important;
        font-size:{fs(16)} !important;
        padding: 11px 18px !important;
        transition: all 0.15s ease !important;
    }}
    [data-testid="stDownloadButton"] > button * {{
        color: inherit !important;
    }}
    [data-testid="stDownloadButton"] > button:hover {{
        filter: brightness(1.08);
    }}
    [data-testid="stDownloadButton"] > button:disabled {{
        opacity: 0.45 !important;
        cursor: not-allowed !important;
        background-color: {toggle_track} !important;
        color: {text_sub} !important;
    }}

    /* ---------------- Stream-launch cards (big, obvious CTAs) ---------------- */
    .stream-card {{
        background-color: {bg_card};
        border: 1.5px solid {border_color};
        border-radius: 16px;
        padding: 32px 28px 26px 28px;
        box-shadow: {shadow};
        text-align: center;
        min-height: 190px;
    }}
    .stream-card .icon-badge {{
        width: 56px; height: 56px;
        border-radius: 14px;
        background-color: {accent}1F;
        display: flex; align-items: center; justify-content: center;
        font-size:{fs(26)};
        margin: 0 auto 14px auto;
    }}
    .st-key-launch_a .stButton > button,
    .st-key-launch_b .stButton > button {{
        background-color: {accent} !important;
        color: {accent_txt_on} !important;
        border: none !important;
        font-weight: 800 !important;
        font-size:{fs(17)} !important;
        padding: 15px 0 !important;
        border-radius: 10px !important;
        margin-top: 18px !important;
        letter-spacing: 0.01em;
    }}
    .st-key-launch_a .stButton > button:hover,
    .st-key-launch_b .stButton > button:hover {{
        filter: brightness(1.08);
        transform: translateY(-1px);
    }}

    /* ---------------- Generic content cards ---------------- */
    .card {{
        background-color: {bg_card} !important;
        padding: 24px !important;
        border-radius: 14px !important;
        border: 1.5px solid {border_color} !important;
        box-shadow: {shadow} !important;
        margin-bottom: 20px !important;
        overflow: hidden;
    }}

    /* ---------------- Status badges ---------------- */
    .badge {{
        padding: 5px 11px;
        border-radius: 6px;
        font-weight: 700;
        font-family: {FONT_MONO};
        font-size:{fs(14)};
        display: inline-block;
        margin: 2px 4px 2px 0;
        border: 1px solid;
    }}
    .badge-red {{
        background-color: {danger_bg};
        color: {danger_txt};
        border-color: {danger_border};
    }}
    .badge-blue {{
        background-color: {info_bg};
        color: {info_txt};
        border-color: {info_border};
    }}
    .badge-green {{
        background-color: {safe_bg};
        color: {safe_txt};
        border-color: {safe_border};
    }}

    /* ---------------- PRI meter ---------------- */
    .meter-row {{ margin-bottom: 16px; }}
    .meter-label {{
        display: flex; justify-content: space-between;
        font-size:{fs(14.5)}; font-weight: 700;
        color: {text_sub}; margin-bottom: 5px;
    }}
    .meter-track {{
        background-color: {toggle_track};
        border-radius: 8px; height: 10px; width: 100%;
        overflow: hidden;
    }}
    .meter-fill {{ height: 10px; border-radius: 8px; }}

    .section-caption {{
        color: {text_sub} !important;
        font-size:{fs(14)} !important;
        font-weight: 700 !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 4px !important;
    }}

    /* ---------------- Card headers with a colored accent stripe ---------------- */
    .card-accent {{
        border-left: 3px solid var(--accent-color, {accent});
        padding-left: 16px;
        margin: -24px -24px 18px -24px;
        padding: 16px 16px 14px 19px;
        border-top-left-radius: 14px;
        border-top-right-radius: 14px;
        border-bottom: 1px solid {border_color};
    }}
    .card-accent h4 {{
        margin: 0 !important;
        font-size:{fs(15.5)} !important;
        font-weight: 700 !important;
        display: flex; align-items: center; gap: 8px;
    }}
    .card-count {{
        margin-left: auto;
        font-family: {FONT_MONO};
        font-size:{fs(12.5)};
        font-weight: 700;
        color: {text_sub};
        background-color: {toggle_track};
        padding: 2px 9px;
        border-radius: 20px;
    }}

    /* ---------------- Organized row lists (leaks / actions / entities) ---------------- */
    .row-list {{
        padding: 4px 22px 6px 22px;
        max-height: 340px;
        overflow-y: auto;
    }}
    .row-item {{
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        row-gap: 6px;
        column-gap: 10px;
        padding: 12px 2px;
        border-bottom: 1px solid {border_color};
    }}
    .row-item:last-child {{ border-bottom: none; }}
    .row-dot {{
        width: 7px; height: 7px; border-radius: 50%;
        flex-shrink: 0;
    }}
    .row-main {{
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 6px;
        min-width: 0;
        flex: 1 1 auto;
    }}
    .row-field {{
        font-family: {FONT_MONO};
        font-size:{fs(14.5)};
        font-weight: 600;
        color: {text_main};
        word-break: break-word;
        overflow-wrap: anywhere;
    }}
    .row-arrow {{
        color: {text_sub};
        font-size:{fs(13)};
        margin: 0 2px;
        flex-shrink: 0;
    }}
    .row-tag {{
        margin-left: auto;
        font-family: {FONT_MONO};
        font-size:{fs(12)};
        font-weight: 700;
        letter-spacing: 0.03em;
        padding: 4px 10px;
        border-radius: 6px;
        border: 1px solid;
        white-space: nowrap;
        flex-shrink: 0;
    }}

    /* ---------------- Consent gate ---------------- */
    /* Streamlit's dialog modal renders in its own overlay and does NOT
       automatically inherit .stApp's background — so without this,
       the modal keeps whatever background Streamlit's native theme
       gives it (often a fixed white), while our text colors are
       theme-conditional (in Dark mode, text_main is a near-white color
       meant to sit on our dark bg_card, not on that default white).
       That mismatch is exactly what would make text unreadable in one
       mode. Forcing the modal's own background to bg_card guarantees
       it's always the correct pairing for text_main/text_sub in
       whichever theme is currently active. */
    div[data-testid="stDialog"] {{
        background-color: {bg_card} !important;
    }}
    div[data-testid="stDialog"] > div {{
        background-color: {bg_card} !important;
    }}
    .consent-section {{
        margin-bottom: 18px;
    }}
    .consent-section h5 {{
        margin: 0 0 6px 0 !important;
        font-size:{fs(15)} !important;
        font-weight: 700 !important;
    }}
    .consent-section p {{
        font-size:{fs(14.5)} !important;
        color: {text_sub} !important;
        line-height: 1.55 !important;
        margin: 0 !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------
# Small render helpers (keep HTML blocks out of the page logic below)
# ------------------------------------------------------------------
def render_html(html: str):
    """Render a block of raw HTML via st.markdown, safely.

    Markdown treats any line indented 4+ spaces as a preformatted code
    block. Building HTML with nested triple-quoted f-strings (especially
    once another function's returned string gets interpolated inside an
    already-indented block) easily pushes a line past that threshold —
    that's exactly what caused a literal "</div>" to show up in a black
    monospace box under the PRI cards. Stripping each line's leading
    whitespace before rendering removes the ambiguity for good.
    """
    flattened = "\n".join(line.strip() for line in html.strip().splitlines())
    st.markdown(flattened, unsafe_allow_html=True)


def card_header(icon, title, color, count=None):
    count_html = f'<span class="card-count">{count}</span>' if count is not None else ""
    return f"""
        <div class="card-accent" style="--accent-color:{color}; background-color:{color}14;">
            <h4 style="color:{color};">{icon} {title}{count_html}</h4>
        </div>
        """


def row_item(field_html, tag_text, tag_color, tag_bg, tag_border, dot_color=None):
    dot_html = f'<span class="row-dot" style="background-color:{dot_color};"></span>' if dot_color else ""
    return f"""
        <div class="row-item">
            <div class="row-main">
                {dot_html}
                {field_html}
            </div>
            <span class="row-tag" style="color:{tag_color}; background-color:{tag_bg}; border-color:{tag_border};">{tag_text}</span>
        </div>
        """


def meter_html(label, value, color_strong, color_track_bg):
    """Return the meter's HTML as a string (does NOT call st.markdown).
    Kept as a string-builder rather than a self-rendering widget so it can
    be concatenated into one combined markdown call with its surrounding
    card — see the note further down about why that matters."""
    return f"""
        <div class="meter-row">
            <div class="meter-label">
                <span>{label}</span>
                <span style="color:{color_strong}; font-weight:700;">{value}%</span>
            </div>
            <div class="meter-track" style="background-color:{color_track_bg};">
                <div class="meter-fill" style="width:{value}%; background-color:{color_strong};"></div>
            </div>
        </div>
        """


def meter(label, value, color_strong, color_track_bg):
    """Standalone version for cases where the meter isn't part of a
    larger combined card block."""
    render_html(meter_html(label, value, color_strong, color_track_bg))


# ------------------------------------------------------------------
# CONSENT & TERMS GATE
# ------------------------------------------------------------------
# Per spec: nothing past this point should be reachable until the user
# explicitly accepts the Privacy Policy, the local-storage/"cookie"
# terms, and the liability disclaimer. This uses st.dialog, which
# renders as a true modal overlay (requires streamlit >= 1.33 — you're
# on 1.62, so you're covered).
@st.dialog("Privacy Policy & Terms", width="large")
def consent_dialog():
    render_html(f"""
        <div class="consent-section">
            <h5>🔒 Privacy Policy</h5>
            <p>All text and CSV processing happens strictly client-side / in-memory
            on this machine. Presidio and spaCy run locally — nothing you type or
            upload is sent to any external server, API, or third party, and MindGuard
            makes no outbound network calls as part of redaction. Nothing you submit
            is retained after your session ends.</p>
        </div>
        """)
    render_html(f"""
        <div class="consent-section">
            <h5>🍪 Cookie &amp; Local Storage Consent</h5>
            <p>MindGuard uses only essential local session storage (no tracking
            cookies, no analytics, no third-party scripts) to remember preferences
            like your Light/Dark theme choice for the current session. This is
            cleared when you close or refresh the browser tab.</p>
        </div>
        """)
    render_html(f"""
        <div class="consent-section">
            <h5>⚖️ Liability Disclaimer</h5>
            <p>MindGuard provides automated redaction <em>assistance</em>. It does
            not guarantee complete removal of all sensitive information, and it does
            not by itself guarantee compliance with any specific regulation
            (including HIPAA or GDPR). You are responsible for independently
            verifying output before relying on it for any compliance purpose.</p>
        </div>
        """)

    agree = st.checkbox(
        "I have read and accept the Privacy Policy, Local Storage Terms, and Liability Disclaimer above."
    )

    if st.button(
        "Accept & Continue",
        type="primary",
        use_container_width=True,
        disabled=not agree,
        key="consent_accept_btn",
    ):
        st.session_state.consent_given = True
        st.session_state.show_terms_review = False
        st.rerun()


if not st.session_state.consent_given or st.session_state.show_terms_review:
    consent_dialog()
    # Hard stop: nothing below this line renders while the gate is up,
    # so Home/Stream A/Stream B and all processing features are
    # genuinely unreachable — not just visually hidden behind the modal.
    st.stop()

# Pre-load the NLP engine here, once, at page-open time — rather than
# letting it lazily load the first time someone clicks "Process &
# Redact Data" mid-interaction (which is what caused Streamlit's own
# raw cache-miss status text, e.g. "Running get_engines().", to flash
# on screen unexpectedly). Since get_engines() is @st.cache_resource,
# this genuinely only does real work once ever per deployment (the
# very first visitor "warms" it for everyone after) — every call after
# that returns instantly with no visible effect at all.
with st.spinner("🛡️ Loading MindGuard's privacy engine…"):
    get_engines()


# ------------------------------------------------------------------
# TOP NAVIGATION HEADER
# ------------------------------------------------------------------
with st.container(key="app_header"):
    nav_col1, nav_col2, nav_col3, nav_col4 = st.columns([3.5, 1.4, 1.6, 1], vertical_alignment="center")

    with nav_col1:
        # Fixed sizes here (not fs()) deliberately — this is the app's
        # branding/chrome, not content the text-size setting is meant
        # to scale. Keeping it fixed means picking "L" can never make
        # the header grow into and collide with the controls beside it.
        render_html(f"""<h2 style="margin:0; padding:0; font-weight:700; font-size:24px; color:{text_main} !important; font-family:{FONT_DISPLAY} !important; white-space:nowrap;">
                🛡️ MindGuard
                <span style="font-weight:400; font-size:16px; color:{text_sub} !important; font-family:{FONT_BODY}; white-space:nowrap;">
                    &nbsp;|&nbsp; Local Anonymization Engine
                </span>
            </h2>""")

    with nav_col2:
        with st.container(key="font_size_toggle"):
            size_cols = st.columns(3)
            for col, (label, scale, btn_key) in zip(size_cols, FONT_SIZE_STEPS):
                with col:
                    with st.container(key=btn_key):
                        if st.button(label, key=f"btn_{btn_key}"):
                            st.session_state.font_scale = scale
                            st.rerun()

    with nav_col3:
        with st.container(key="theme_toggle"):
            t1, t2 = st.columns(2)
            with t1:
                with st.container(key="theme_light_btn"):
                    if st.button("☀️ Light", key="btn_light", use_container_width=True):
                        toggle_theme("Light")
                        st.rerun()
            with t2:
                with st.container(key="theme_dark_btn"):
                    if st.button("🌙 Dark", key="btn_dark", use_container_width=True):
                        toggle_theme("Dark")
                        st.rerun()

    with nav_col4:
        if st.session_state.page != "Home":
            st.button("🏠 Home", on_click=set_page, args=("Home",), use_container_width=True)

# ------------------------------------------------------------------
# PAGE 1: HOME
# ------------------------------------------------------------------
if st.session_state.page == "Home":
    render_html(f"""<h2 style="text-align:center; color:{text_main}; margin-bottom:6px; font-weight:700;
                       font-family:{FONT_BODY}; letter-spacing:normal;">
            Select a Data Stream for Local Scrubbing
        </h2>
        <p style="text-align:center; color:{text_sub}; margin-bottom:32px; font-size:{fs(16)};">
            Everything below runs on this machine — nothing leaves the host.
        </p>""")

    col1, col2 = st.columns(2, gap="large")

    with col1:
        render_html(f"""
            <div class="stream-card">
                <div class="icon-badge">💬</div>
                <h3 style="margin-bottom:8px; font-weight:700; font-size:{fs(19)};">Interactive Chat Stream</h3>
                <p style="color:{text_sub} !important; font-size:{fs(14.5)}; line-height:1.5;">
                    Redact unstructured conversation text and personal entities in real time.
                </p>
            </div>
            """)
        with st.container(key="launch_a"):
            st.button(
                "Launch Stream A  →",
                key="home_stream_a",
                use_container_width=True,
                on_click=set_page,
                args=("Stream A",),
            )

    with col2:
        render_html(f"""
            <div class="stream-card">
                <div class="icon-badge">📊</div>
                <h3 style="margin-bottom:8px; font-weight:700; font-size:{fs(19)};">Apple Health Export</h3>
                <p style="color:{text_sub} !important; font-size:{fs(14.5)}; line-height:1.5;">
                    Scrub metadata, serial identifiers, and fine timestamps from CSV datasets.
                </p>
            </div>
            """)
        with st.container(key="launch_b"):
            st.button(
                "Launch Stream B  →",
                key="home_stream_b",
                use_container_width=True,
                on_click=set_page,
                args=("Stream B",),
            )

    st.write("")

    footer_col1, footer_col2 = st.columns([3, 1])
    with footer_col1:
        render_html(f"""<p style="text-align:left; color:{text_sub} !important; font-size:{fs(12.5)};">
                © 2026 MindGuard Systems &nbsp;·&nbsp; All operations execute strictly on client hardware.
            </p>""")
    with footer_col2:
        if st.button("📄 Privacy Policy & Terms", key="review_terms_btn", use_container_width=True):
            st.session_state.show_terms_review = True
            st.rerun()

# ------------------------------------------------------------------
# PAGE 2: STREAM A — INTERACTIVE CHAT
# ------------------------------------------------------------------
elif st.session_state.page == "Stream A":
    render_html(f"""<p class="section-caption">MindGuard &nbsp;›&nbsp; Stream A: Interactive Chat</p>""")

    if "stream_a_result" not in st.session_state:
        st.session_state.stream_a_result = None
    if "stream_a_input" not in st.session_state:
        st.session_state.stream_a_input = ""

    def clear_stream_a():
        st.session_state.stream_a_input = ""
        st.session_state.stream_a_result = None

    col_in, col_out = st.columns(2, gap="large")

    with col_in:
        st.markdown("#### 📄 Raw Input Text")
        user_input = st.text_area(
            "Raw Text Input",
            key="stream_a_input",
            placeholder="Paste or type text to scan for PII…",
            height=250,
            label_visibility="collapsed",
        )

        btn_col1, btn_col2 = st.columns([2.4, 1])
        with btn_col1:
            process_clicked = st.button(
                "🛡️ Process & Redact Data",
                type="primary",
                use_container_width=True,
                key="redact_btn",
                disabled=not user_input.strip(),
            )
        with btn_col2:
            st.button(
                "🧹 Clear",
                use_container_width=True,
                key="clear_btn",
                on_click=clear_stream_a,
            )

        if process_clicked:
            # A spinner instead of letting whatever Streamlit/Presidio's
            # default loading state looks like show through, and a
            # try/except so a real error becomes a clean message instead
            # of a raw traceback flashing on screen.
            with st.spinner("🛡️ Scanning for PII…"):
                try:
                    sanitized_text, entities = redact_text(user_input)
                    st.session_state.stream_a_result = {
                        "input_text": user_input,
                        "sanitized_text": sanitized_text,
                        "entities": entities,
                        "pri": calculate_pri_reduction(entities),
                    }
                except Exception as e:
                    st.error(f"Something went wrong while processing this text: {e}")

    with col_out:
        st.markdown("#### 👁️ Sanitized Output & Metrics")
        result = st.session_state.stream_a_result

        st.text_area(
            "Anonymized Output",
            value=result["sanitized_text"] if result else "",
            placeholder="Redacted output will appear here after processing.",
            height=120,
            disabled=True,
            label_visibility="collapsed",
        )

        if result and result["entities"]:
            entity_rows = "".join(
                row_item(
                    f'<span class="row-field">{result["input_text"][e.start:e.end]}</span>',
                    e.entity_type, info_txt, info_bg, info_border,
                    dot_color=info_txt,
                )
                for e in result["entities"]
            )
            render_html(f"""
                <div class="card" style="padding-bottom:6px;">
                    {card_header("🔎", "Identified Entities", info_txt, count=len(result["entities"]))}
                    <div class="row-list">{entity_rows}</div>
                </div>
                """)
        else:
            render_html(f"""
                <div class="card" style="padding-bottom:6px;">
                    {card_header("🔎", "Identified Entities", info_txt, count=0)}
                    <p style="color:{text_sub} !important; font-size:{fs(14)}; padding:4px 22px 14px 22px; margin:0 !important;">
                        {"No entities detected in the last scan." if result else "Nothing processed yet — enter text and click Process &amp; Redact Data."}
                    </p>
                </div>
                """)

        with st.container(key="pri_card_a"):
            # Built as ONE combined render_html call (header + both meters)
            # instead of open-div / meter() / close-div across three
            # separate st.markdown calls — that was the cause of the PRI
            # scores rendering underneath the white card instead of
            # inside it: each st.markdown() produces its own independent
            # DOM node, so an opening <div> in one call and a closing
            # </div> in a later call never actually wrap the elements
            # rendered in between (same root cause as the header bug).
            pri = result["pri"] if result else {"raw_pri": 0, "redacted_pri": 0}
            render_html(f"""
                <div class="card">
                    <h5 style="margin-top:0; margin-bottom:16px; font-weight:700; letter-spacing:0.04em;
                                font-size:{fs(14)}; text-transform:uppercase; color:{text_sub} !important;">
                        Privacy Risk Index
                    </h5>
                    {meter_html("Raw PRI Risk Index", pri["raw_pri"], danger_txt, danger_bg)}
                    {meter_html("Post-Redaction PRI Score", pri["redacted_pri"], safe_txt, safe_bg)}
                </div>
                """)

# ------------------------------------------------------------------
# PAGE 3: STREAM B — APPLE HEALTH CSV
# ------------------------------------------------------------------
elif st.session_state.page == "Stream B":
    render_html(f"""<p class="section-caption">MindGuard &nbsp;›&nbsp; Stream B: CSV Export Scrubbing</p>""")

    if "stream_b_result" not in st.session_state:
        st.session_state.stream_b_result = None

    uploaded_file = st.file_uploader(
        "Upload health_data.csv",
        type=["csv"],
        help=f"Supports files with 800,000+ record entries, up to {MAX_UPLOAD_SIZE_MB}MB.",
    )

    # File size validation, per spec. uploaded_file.size is in bytes.
    file_too_large = False
    if uploaded_file is not None:
        file_size_mb = uploaded_file.size / (1024 * 1024)
        if uploaded_file.size > MAX_UPLOAD_SIZE_BYTES:
            file_too_large = True
            st.error(
                f"This file is {file_size_mb:.1f}MB, which is over the "
                f"{MAX_UPLOAD_SIZE_MB}MB limit. Please upload a smaller export."
            )

    st.write("")

    if st.button(
        "🔍 Scan & Scrub CSV",
        type="primary",
        use_container_width=True,
        key="scrub_btn",
        disabled=uploaded_file is None or file_too_large,
    ):
        with st.spinner("🔍 Scanning columns for PII…"):
            try:
                df = pd.read_csv(uploaded_file)
                scrubbed_df, classified, actions = process_health_csv(df)
            except Exception as e:
                st.error(f"Something went wrong while processing this file: {e}")
            else:
                st.session_state.stream_b_result = {
                    "scrubbed_df": scrubbed_df,
                    "classified": classified,
                    "actions": actions,
                    "pri": calculate_csv_pri_reduction(classified),
                    "row_count": len(df),
                }

    st.write("")

    result = st.session_state.stream_b_result
    c1, c2, c3 = st.columns(3, gap="medium")

    with c1:
        if result:
            leak_cols = [col for cols in result["classified"].values() for col in cols]
        else:
            leak_cols = []

        if leak_cols:
            leak_rows = "".join(
                row_item(
                    f'<span class="row-field">{col}</span>',
                    "FLAGGED", danger_txt, danger_bg, danger_border,
                    dot_color=danger_txt,
                )
                for col in leak_cols
            )
            body = f'<div class="row-list">{leak_rows}</div>'
        else:
            empty_msg = "No risky columns detected." if result else "Upload and scan a CSV to see detected leaks here."
            body = f'<p style="color:{text_sub} !important; font-size:{fs(14)}; padding:4px 22px 14px 22px; margin:0 !important;">{empty_msg}</p>'

        render_html(f"""
            <div class="card" style="min-height:270px; padding-bottom:6px;">
                {card_header("⚠️", "Detected Leaks", danger_txt, count=len(leak_cols))}
                {body}
            </div>
            """)

    with c2:
        actions_list = result["actions"] if result else []
        if actions_list:
            action_rows = "".join(
                row_item(
                    f'<span class="row-field">{col}</span>',
                    status, safe_txt, safe_bg, safe_border,
                    dot_color=safe_txt,
                )
                for col, status in actions_list
            )
            body = f'<div class="row-list">{action_rows}</div>'
        else:
            empty_msg = "Nothing to scrub in this file." if result else "Actions taken during scrubbing will appear here."
            body = f'<p style="color:{text_sub} !important; font-size:{fs(14)}; padding:4px 22px 14px 22px; margin:0 !important;">{empty_msg}</p>'

        render_html(f"""
            <div class="card" style="min-height:270px; padding-bottom:6px;">
                {card_header("🛠️", "Actions Applied", info_txt, count=len(actions_list))}
                {body}
            </div>
            """)

    with c3:
        with st.container(key="pri_card_b"):
            pri = result["pri"] if result else {"raw_pri": 0, "redacted_pri": 0}
            render_html(f"""
                <div class="card" style="min-height:270px;">
                    <h4 style="color:{text_main} !important; margin-top:0; margin-bottom:16px; font-weight:700; font-size:{fs(16)};">
                        📊 Batch Privacy Score
                    </h4>
                    {meter_html("Raw PRI Risk Index", pri["raw_pri"], danger_txt, danger_bg)}
                    {meter_html("Post-Redaction PRI", pri["redacted_pri"], safe_txt, safe_bg)}
                </div>
                """)

        # Real in-memory CSV export — no temp files written to disk,
        # matching the Data Persistence Safeguards requirement. Disabled
        # until a scan has actually produced a result.
        csv_bytes = (
            result["scrubbed_df"].to_csv(index=False).encode("utf-8")
            if result else b""
        )
        st.download_button(
            "📥 Export Sanitized CSV",
            data=csv_bytes,
            file_name="sanitized_health_data.csv",
            mime="text/csv",
            type="primary",
            use_container_width=True,
            key="download_btn",
            disabled=result is None,
        )