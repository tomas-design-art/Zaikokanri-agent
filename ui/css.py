"""
CSS管理モジュール

表示サイズ（小/中/大）に応じたCSS変数を生成・適用する。
"""

import streamlit as st


def apply_size_css(size_mode: str):
    """表示サイズに応じたCSSを適用（CSS変数ベース）"""

    if size_mode == "小":
        base_font = "13px"
        heading1, heading2, heading3 = "2.0rem", "1.6rem", "1.3rem"
        metric_label, metric_value = "11px", "18px"
        gap, padding = "0.4rem", "0.25rem 0.6rem"
    elif size_mode == "中":
        base_font = "16px"
        heading1, heading2, heading3 = "2.6rem", "2.0rem", "1.6rem"
        metric_label, metric_value = "14px", "28px"
        gap, padding = "0.6rem", "0.4rem 0.9rem"
    else:  # 大
        base_font = "22px"
        heading1, heading2, heading3 = "3.6rem", "2.8rem", "2.2rem"
        metric_label, metric_value = "20px", "42px"
        gap, padding = "0.8rem", "0.6rem 1.4rem"

    css = f"""
    <style>
    :root {{
        --base-font: {base_font};
        --heading1: {heading1};
        --heading2: {heading2};
        --heading3: {heading3};
        --metric-label: {metric_label};
        --metric-value: {metric_value};
        --gap: {gap};
        --padding: {padding};
    }}
    .block-container {{
        max-width: 100% !important;
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
    }}
    .center-card {{
        max-width: 720px;
        margin: 0 auto;
    }}
    @media (max-width: 720px) {{
        .center-card {{ max-width: 100%; }}
    }}
    h1 {{ font-size: var(--heading1) !important; }}
    h2 {{ font-size: var(--heading2) !important; }}
    h3 {{ font-size: var(--heading3) !important; }}
    [data-testid="stSidebar"] h1 {{
        font-size: 1.6rem !important;
    }}
    body, p, span, label {{
        font-size: var(--base-font);
    }}
    [data-testid="stSidebar"] {{
        font-size: var(--base-font) !important;
    }}
    [data-testid="stSidebar"] .stRadio label,
    [data-testid="stSidebar"] .stSelectbox label {{
        font-size: var(--base-font) !important;
    }}
    .stTabs [data-baseweb="tab"] {{
        font-size: var(--base-font) !important;
        padding: var(--padding) !important;
    }}
    .stButton > button {{
        font-size: var(--base-font) !important;
        padding: var(--padding) !important;
    }}
    [data-testid="stMetricLabel"] {{
        font-size: var(--metric-label) !important;
    }}
    [data-testid="stMetricValue"] {{
        font-size: var(--metric-value) !important;
    }}
    .stTextInput > label,
    .stNumberInput > label,
    .stSelectbox > label,
    .stTextArea > label {{
        font-size: var(--base-font) !important;
        margin-bottom: var(--gap) !important;
    }}
    .stTextInput input,
    .stNumberInput input,
    .stTextArea textarea {{
        font-size: var(--base-font) !important;
        padding: var(--gap) !important;
    }}
    .stSelectbox > div > div {{
        font-size: var(--base-font) !important;
    }}
    .stMarkdown {{
        font-size: var(--base-font) !important;
    }}
    .stMarkdown p {{
        font-size: var(--base-font) !important;
        margin-bottom: var(--gap) !important;
    }}
    .stAlert {{
        font-size: var(--base-font) !important;
        padding: var(--gap) !important;
    }}
    .stAlert p {{
        font-size: var(--base-font) !important;
    }}
    .stDataFrame, .stDataEditor {{
        font-size: var(--base-font) !important;
    }}
    div[data-testid="stDataFrame"] table {{
        font-size: var(--base-font) !important;
    }}
    div[data-testid="stDataFrame"] th,
    div[data-testid="stDataFrame"] td {{
        font-size: var(--base-font) !important;
        padding: var(--gap) !important;
    }}
    div[data-testid="stDataFrame"] input {{
        font-size: var(--base-font) !important;
    }}
    .stCaption, [data-testid="stCaptionContainer"] {{
        font-size: calc(var(--base-font) - 2px) !important;
    }}
    [data-testid="stVerticalBlockBorderWrapper"] {{
        padding: var(--gap) !important;
    }}
    hr {{
        margin-top: var(--gap) !important;
        margin-bottom: var(--gap) !important;
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
