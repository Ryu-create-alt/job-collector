import html as html_mod
import sys
import urllib.parse
import streamlit as st
import pandas as pd
import sqlite3
import os

# tools/job-collector/ をパスに追加（ローカル・Streamlit Cloud 両対応）
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_TOOL_DIR = os.path.dirname(_SRC_DIR)
if _TOOL_DIR not in sys.path:
    sys.path.insert(0, _TOOL_DIR)

from src.filter import extract_prefecture, clean_text, parse_experience_years

# ─── ヘルパー ────────────────────────────────────────────────────────────────

def _e(text) -> str:
    return html_mod.escape(str(text) if text is not None else "")

def _safe_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(str(url))
        if parsed.scheme in ("http", "https"):
            return _e(url)
    except Exception:
        pass
    return "#"

# ─── DB ─────────────────────────────────────────────────────────────────────

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_BASE_DIR, "jobs.db")

def load_data() -> pd.DataFrame:
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM jobs ORDER BY updated_at DESC", conn)
    conn.close()
    if df.empty:
        return df
    df['is_network_engineer'] = df['is_network_engineer'].astype(bool)
    df['is_dispatched']       = df['is_dispatched'].astype(bool)
    df['passed_filters']      = df['passed_filters'].astype(bool)
    df['prefecture']          = df['location'].apply(extract_prefecture)
    df['experience_years']    = df['description'].apply(parse_experience_years)
    return df

# ─── ページ設定 ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="社内NWエンジニア 求人ダッシュボード",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS ─────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
.block-container { padding-top: 1.8rem; }

.job-card {
    background: #ffffff;
    border-radius: 10px;
    padding: 18px 22px 14px;
    margin-bottom: 12px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    border: 1px solid #e2e8f0;
    border-left: 5px solid #3b82f6;
}
.job-card.failed { border-left-color: #cbd5e1; }

.card-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 3px;
}
.company   { font-size: 12px; color: #64748b; font-weight: 600; }
.date-info { font-size: 11px; color: #94a3b8; text-align: right; flex-shrink: 0; margin-left: 12px; }

.job-title       { font-size: 16px; font-weight: 700; color: #1e40af; margin: 4px 0 11px; line-height: 1.45; }
.job-title.muted { color: #475569; }

.badges { margin-bottom: 11px; line-height: 2; }
.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 99px;
    font-size: 11px;
    font-weight: 600;
    margin: 2px 3px 2px 0;
    white-space: nowrap;
}
.b-blue   { background: #dbeafe; color: #1d4ed8; }
.b-green  { background: #dcfce7; color: #15803d; }
.b-yellow { background: #fef9c3; color: #854d0e; }
.b-red    { background: #fee2e2; color: #b91c1c; }
.b-gray   { background: #f1f5f9; color: #475569; }

.card-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 11px;
    padding-top: 10px;
    border-top: 1px solid #f1f5f9;
}
.location { font-size: 13px; color: #475569; }

.apply-btn {
    background: #2563eb;
    color: #fff !important;
    padding: 7px 16px;
    border-radius: 7px;
    text-decoration: none;
    font-size: 13px;
    font-weight: 600;
    white-space: nowrap;
}
.apply-btn:hover    { background: #1d4ed8; }
.apply-btn.disabled { background: #94a3b8; pointer-events: none; }

.desc-preview {
    font-size: 13px;
    color: #4b5563;
    line-height: 1.65;
    padding: 10px 13px;
    background: #f8fafc;
    border-radius: 6px;
    margin-bottom: 10px;
    white-space: pre-wrap;
    word-break: break-all;
}
</style>
""", unsafe_allow_html=True)

# ─── ヘッダー ────────────────────────────────────────────────────────────────

st.title("🌐 社内NWエンジニア 求人ダッシュボード")
st.caption("大手上場企業の公式採用ページから収集した「社内NW・正社員・自社勤務」求人の一覧")

# ─── データ読み込み ───────────────────────────────────────────────────────────

df = load_data()

if df.empty:
    st.info("求人データがありません。`python run.py` を実行してください。")
    st.stop()

# ─── サイドバー ──────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("絞り込み")

    st.markdown("**表示対象**")
    status_filter = st.radio(
        "表示対象",
        ["おすすめのみ", "すべて", "不適合のみ"],
        index=0,
        label_visibility="collapsed",
    )

    st.divider()

    st.markdown("**勤務地（都道府県）**")
    all_prefs = sorted(df['prefecture'].unique())
    selected_prefs = st.multiselect(
        "都道府県", all_prefs, default=all_prefs, label_visibility="collapsed",
    )

    st.divider()

    st.markdown("**必要経験年数の上限**")
    max_exp = st.slider(
        "経験年数上限", min_value=0, max_value=10, value=10,
        format="%d年", label_visibility="collapsed",
    )
    if max_exp == 10:
        st.caption("すべての求人を表示")
    elif max_exp == 0:
        st.caption("年数不明・未経験可のみ表示")
    else:
        st.caption(f"{max_exp}年以下（年数不明は常に表示）")

    st.divider()

    h_min = int(df['holiday_count'].min())
    h_max = int(df['holiday_count'].max())
    st.markdown("**年間休日数（下限）**")
    if h_min < h_max:
        min_holiday = st.slider(
            "最低年間休日", h_min, h_max,
            h_min if h_min > 0 else 110,
            format="%d日", label_visibility="collapsed",
        )
    else:
        min_holiday = h_min
        st.caption(f"{h_min}日（データが1種類のみ）")

    st.divider()

    st.markdown("**キーワード検索**")
    keyword = st.text_input(
        "キーワード", placeholder="例: VPN, 東京, CCNA",
        label_visibility="collapsed",
    )

# ─── フィルタリング ───────────────────────────────────────────────────────────

fdf = df.copy()

if status_filter == "おすすめのみ":
    fdf = fdf[fdf['passed_filters']]
elif status_filter == "不適合のみ":
    fdf = fdf[~fdf['passed_filters']]

if selected_prefs:
    fdf = fdf[fdf['prefecture'].isin(selected_prefs)]

# 経験年数：年数不明(0)は常に表示、max_exp=10 は制限なし
if max_exp < 10:
    fdf = fdf[(fdf['experience_years'] == 0) | (fdf['experience_years'] <= max_exp)]

if h_min < h_max:
    fdf = fdf[fdf['holiday_count'] >= min_holiday]

if keyword:
    q = clean_text(keyword)
    mask = (
        fdf['title'].str.lower().str.contains(q, na=False, regex=False) |
        fdf['description'].str.lower().str.contains(q, na=False, regex=False) |
        fdf['company_name'].str.lower().str.contains(q, na=False, regex=False)
    )
    fdf = fdf[mask]

# ─── メトリクス ──────────────────────────────────────────────────────────────

c1, c2, c3, c4 = st.columns(4)
c1.metric("総収集件数",   f"{len(df):,} 件")
c2.metric("おすすめ件数", f"{int(df['passed_filters'].sum()):,} 件")
c3.metric("対象企業数",   f"{df['company_name'].nunique():,} 社")
c4.metric("現在表示中",   f"{len(fdf):,} 件")

st.divider()

# ─── 求人カード ──────────────────────────────────────────────────────────────

if fdf.empty:
    st.warning("条件に合う求人が見つかりませんでした。フィルターを緩めてみてください。")
else:
    for _, row in fdf.iterrows():
        passed   = bool(row['passed_filters'])
        card_cls = "job-card" if passed else "job-card failed"
        ttl_cls  = "job-title" if passed else "job-title muted"
        exp      = int(row['experience_years'])
        hc       = int(row['holiday_count'])
        url      = _safe_url(row.get('job_url') or '')
        updated  = str(row.get('updated_at', ''))[:10]
        loc      = _e(row.get('location') or '勤務地不明')
        emp      = _e(row.get('employment_type') or '不明')

        badges = ""
        if passed:
            badges += '<span class="badge b-blue">✨ おすすめ</span>'
        badges += f'<span class="badge b-gray">💼 {emp}</span>'
        if hc >= 120:
            badges += f'<span class="badge b-green">📅 年休{hc}日</span>'
        elif hc > 0:
            badges += f'<span class="badge b-yellow">📅 年休{hc}日</span>'
        else:
            badges += '<span class="badge b-gray">📅 年休不明</span>'
        if exp > 0:
            badges += f'<span class="badge b-yellow">📋 経験{exp}年以上</span>'
        else:
            badges += '<span class="badge b-gray">📋 経験年数不明</span>'
        if bool(row['is_dispatched']):
            badges += '<span class="badge b-red">⚠️ 常駐の可能性あり</span>'
        else:
            badges += '<span class="badge b-green">🏠 自社勤務</span>'

        btn_cls   = "apply-btn" if url != "#" else "apply-btn disabled"
        btn_label = "求人ページを開く →" if url != "#" else "URL未取得"
        desc      = _e(row.get('description') or "")

        st.markdown(f"""
<div class="{card_cls}">
  <div class="card-header">
    <span class="company">{_e(row['company_name'])}</span>
    <span class="date-info">更新: {_e(updated)}</span>
  </div>
  <div class="{ttl_cls}">{_e(row['title'])}</div>
  <div class="badges">{badges}</div>
  <div class="desc-preview">{desc}</div>
  <div class="card-footer">
    <span class="location">📍 {loc}</span>
    <a href="{url}" target="_blank" class="{btn_cls}">{btn_label}</a>
  </div>
</div>
""", unsafe_allow_html=True)

        with st.expander("休日情報の詳細"):
            st.write(row.get('holiday_text') or "取得できませんでした")
