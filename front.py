import streamlit as st

# Page Configuration
st.set_page_config(
    page_title="MindGuard Portal",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Initialize navigation session state if not set
if "page" not in st.session_state:
    st.session_state.page = "Home"


# Callback functions to change pages
def set_page(page_name):
    st.session_state.page = page_name


# CSS Overrides for Dark Elements & Custom Styling
st.markdown(
    """
    <style>
    /* Global Page Background */
    .stApp {
        background-color: #e7f5ff !important;
    }
    
    /* Global Typography */
    h1, h2, h3, h4, h5, h6, p, span, label, div {
        color: #1e293b !important;
    }
    
    /* Fix Text Areas (Active & Disabled for Safari) */
    .stTextArea textarea {
        background-color: #ffffff !important;
        color: #0f172a !important;
        -webkit-text-fill-color: #0f172a !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 12px !important;
        font-size: 15px !important;
        opacity: 1 !important;
    }
    
    .stTextArea textarea:disabled {
        background-color: #ffffff !important;
        color: #0f172a !important;
        -webkit-text-fill-color: #0f172a !important;
        opacity: 1 !important;
    }
    
    /* Fix Code Badges styling */
    code {
        background-color: #e0f2fe !important;
        color: #0284c7 !important;
        padding: 2px 6px !important;
        border-radius: 4px !important;
    }
    
    /* Fix Drag & Drop File Upload Box */
    [data-testid="stFileUploader"] {
        background-color: #ffffff !important;
        border: 2px dashed #0284c7 !important;
        border-radius: 12px !important;
        padding: 20px !important;
    }
    
    [data-testid="stFileUploader"] * {
        color: #0f172a !important;
        background-color: transparent !important;
    }
    
    /* Fix Buttons */
    .stButton > button {
        background-color: #ffffff !important;
        color: #0f172a !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 10px 20px !important;
        transition: all 0.2s ease !important;
    }
    
    .stButton > button:hover {
        background-color: #f1f5f9 !important;
        border-color: #0284c7 !important;
        color: #0284c7 !important;
    }

    /* Primary Action Buttons (Redact & Download) */
    .stButton > button[kind="primary"] {
        background-color: #00c48c !important;
        color: #ffffff !important;
        border: none !important;
        font-weight: 700 !important;
    }
    
    .stButton > button[kind="primary"]:hover {
        background-color: #00ab7a !important;
        color: #ffffff !important;
    }
    
    /* Custom White Card Containers */
    .white-card {
        background-color: #ffffff !important;
        padding: 24px !important;
        border-radius: 16px !important;
        border: 1px solid #cbd5e1 !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.03) !important;
        margin-bottom: 20px !important;
    }
    
    /* Custom Badges */
    .badge-red {
        background-color: #ffe4e6 !important;
        color: #e11d48 !important;
        padding: 6px 12px;
        border-radius: 6px;
        font-weight: 700;
        font-size: 13px;
        display: inline-block;
        margin-bottom: 6px;
    }
    
    .badge-blue {
        background-color: #e0f2fe !important;
        color: #0284c7 !important;
        padding: 6px 12px;
        border-radius: 6px;
        font-weight: 700;
        font-size: 13px;
        display: inline-block;
        margin-bottom: 6px;
    }
    </style>
""",
    unsafe_allow_html=True,
)

# Top Navigation Bar
nav_col1, nav_col2 = st.columns([4, 1])
with nav_col1:
    st.markdown("## 🛡️ **MindGuard** Portal")
with nav_col2:
    if st.session_state.page != "Home":
        st.button("🏠 Back to Home", on_click=set_page, args=("Home",))

st.divider()

# ---------------------------------------------------------
# PAGE 1: HOME SELECTION
# ---------------------------------------------------------
if st.session_state.page == "Home":
    st.markdown(
        "<h2 style='text-align: center; color: #0f172a; margin-bottom: 30px;'>Choose a data stream to evaluate local redaction</h2>",
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            """
<div class="white-card" style="text-align: center; min-height: 220px;">
    <div style="font-size: 36px; margin-bottom: 10px;">💬</div>
    <h3 style="margin-bottom: 10px;">Interactive Chat</h3>
    <p style="color: #475569 !important; font-size: 14px;">Redact text & PII in real time using our advanced local processing engine.</p>
</div>
""",
            unsafe_allow_html=True,
        )
        st.button(
            "Stream A",
            key="home_stream_a",
            use_container_width=True,
            on_click=set_page,
            args=("Stream A",),
        )

    with col2:
        st.markdown(
            """
<div class="white-card" style="text-align: center; min-height: 220px;">
    <div style="font-size: 36px; margin-bottom: 10px;">📊</div>
    <h3 style="margin-bottom: 10px;">Apple Health CSV</h3>
    <p style="color: #475569 !important; font-size: 14px;">Scrub device metadata and sensitive identifiers from Apple HealthKit exports.</p>
</div>
""",
            unsafe_allow_html=True,
        )
        st.button(
            "Stream B",
            key="home_stream_b",
            use_container_width=True,
            on_click=set_page,
            args=("Stream B",),
        )

    st.write("")
    st.write("")
    st.markdown(
        "<p style='text-align: center; color: #64748b !important; font-size: 13px;'>© 2026 MindGuard Systems. All data processed locally.</p>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------
# PAGE 2: STREAM A — INTERACTIVE CHAT
# ---------------------------------------------------------
elif st.session_state.page == "Stream A":
    st.caption("MindGuard > **Stream A: Interactive Chat**")

    col_in, col_out = st.columns(2)

    with col_in:
        st.markdown("### 📄 Input Text (Raw Data)")
        user_input = st.text_area(
            "Raw Text Input",
            value="Hi, my name is Alex. You can call me at (222) 222-2222.",
            height=260,
            label_visibility="collapsed",
        )
        st.button(
            "🛡️ Redact text",
            type="primary",
            use_container_width=True,
            key="redact_btn",
        )

    with col_out:
        st.markdown("### 👁️ Detected entities & output")

        st.text_area(
            "Anonymized Output",
            value="Hi, my name is [PERSON]. You can call me at [PHONE NUMBER].",
            height=110,
            disabled=True,
            label_visibility="collapsed",
        )

        # Non-indented raw HTML string to prevent markdown code block formatting
        stream_a_card = """
<div class="white-card">
    <h5 style="margin-top: 0; margin-bottom: 12px; font-weight: 700; letter-spacing: 0.5px; color: #0f172a !important;">DETECTED ENTITIES</h5>
    <div style="margin-bottom: 20px;">
        <span class="badge-blue">Alex</span> <code style="color: #0284c7 !important;">[PERSON]</code> &nbsp;&nbsp;&nbsp; 
        <span class="badge-blue">(222) 222-2222</span> <code style="color: #0284c7 !important;">[PHONE NUMBER]</code>
    </div>
    <div style="margin-bottom: 14px;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
            <span style="font-size: 13px; font-weight: 600; color: #334155 !important;">Raw PRI Risk Score</span>
            <span style="font-size: 13px; font-weight: 700; color: #dc2626 !important;">89%</span>
        </div>
        <div style="background-color: #fee2e2; border-radius: 8px; height: 10px; width: 100%;">
            <div style="background-color: #dc2626; border-radius: 8px; height: 10px; width: 89%;"></div>
        </div>
    </div>
    <div>
        <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
            <span style="font-size: 13px; font-weight: 600; color: #334155 !important;">New PRI Risk Score</span>
            <span style="font-size: 13px; font-weight: 700; color: #16a34a !important;">14%</span>
        </div>
        <div style="background-color: #dcfce7; border-radius: 8px; height: 10px; width: 100%;">
            <div style="background-color: #00c48c; border-radius: 8px; height: 10px; width: 14%;"></div>
        </div>
    </div>
</div>
"""
        st.markdown(stream_a_card, unsafe_allow_html=True)

# ---------------------------------------------------------
# PAGE 3: STREAM B — APPLE HEALTH CSV
# ---------------------------------------------------------
elif st.session_state.page == "Stream B":
    st.caption("MindGuard > **Stream B: Apple Health CSV Cleaner**")

    # Drag & Drop File Upload Box
    uploaded_file = st.file_uploader(
        "Drag & Drop health_data.csv",
        type=["csv"],
        help="800,000+ records loaded",
    )

    st.write("")

    # 3 Summary Cards
    c1, c2, c3 = st.columns(3)

    with c1:
        card_leaks = """
<div class="white-card" style="min-height: 230px;">
    <h4 style="color: #dc2626 !important; margin-top:0;">⚠️ DETECTED LEAKS</h4>
    <div style="margin-top: 15px;">
        <p><span class="badge-red">sourceName</span></p>
        <p><span class="badge-red">device</span></p>
        <p><span class="badge-red">m_startTime</span></p>
        <p><span class="badge-red">m_creationTimeZone</span></p>
    </div>
</div>
"""
        st.markdown(card_leaks, unsafe_allow_html=True)

    with c2:
        card_actions = """
<div class="white-card" style="min-height: 230px;">
    <h4 style="color: #0284c7 !important; margin-top:0;">🛠️ ACTIONS APPLIED</h4>
    <div style="margin-top: 15px;">
        <p style="font-size: 14px;">Serials: <span class="badge-blue">MASKED</span></p>
        <p style="font-size: 14px;">Timestamps: <span class="badge-blue">GENERALIZED</span></p>
        <p style="font-size: 14px;">GPS Data: <span class="badge-blue">STRIPPED</span></p>
    </div>
</div>
"""
        st.markdown(card_actions, unsafe_allow_html=True)

    with c3:
        card_scores = """
<div class="white-card" style="min-height: 230px;">
    <h4 style="color: #0f172a !important; margin-top:0; margin-bottom: 20px;">📊 BATCH PRIVACY SCORE</h4>
    <div style="margin-bottom: 14px;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
            <span style="font-size: 13px; font-weight: 600; color: #334155 !important;">Raw PRI Risk Score</span>
            <span style="font-size: 13px; font-weight: 700; color: #dc2626 !important;">89%</span>
        </div>
        <div style="background-color: #fee2e2; border-radius: 8px; height: 10px; width: 100%;">
            <div style="background-color: #dc2626; border-radius: 8px; height: 10px; width: 89%;"></div>
        </div>
    </div>
    <div style="margin-bottom: 10px;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
            <span style="font-size: 13px; font-weight: 600; color: #334155 !important;">New PRI Risk Score</span>
            <span style="font-size: 13px; font-weight: 700; color: #16a34a !important;">14%</span>
        </div>
        <div style="background-color: #dcfce7; border-radius: 8px; height: 10px; width: 100%;">
            <div style="background-color: #00c48c; border-radius: 8px; height: 10px; width: 14%;"></div>
        </div>
    </div>
</div>
"""
        st.markdown(card_scores, unsafe_allow_html=True)
        st.button(
            "📥 Download New CSV",
            type="primary",
            use_container_width=True,
            key="download_btn",
        )
