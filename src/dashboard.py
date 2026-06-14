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

from src.filter import extract_prefecture, clean_text

def _e(text) -> str:
    """HTML特殊文字をエスケープする（XSS対策）。"""
    return html_mod.escape(str(text) if text is not None else "")

def _safe_url(url: str) -> str:
    """http/https のみ許可し、それ以外は '#' に差し替える（URLインジェクション対策）。"""
    try:
        parsed = urllib.parse.urlparse(str(url))
        if parsed.scheme in ("http", "https"):
            return _e(url)
    except Exception:
        pass
    return "#"

# スクリプト位置を基点にパスを解決する（実行ディレクトリに依存しない）
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# データベースパス
DB_PATH = os.path.join(_BASE_DIR, "jobs.db")

def load_data():
    """データベースから求人データを読み込み、Pandas DataFrame に変換します。"""
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
        
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT * FROM jobs ORDER BY updated_at DESC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    if not df.empty:
        # boolean型の変換 (SQLiteは0/1なので)
        df['is_network_engineer'] = df['is_network_engineer'].astype(bool)
        df['is_dispatched'] = df['is_dispatched'].astype(bool)
        df['passed_filters'] = df['passed_filters'].astype(bool)
        
        # 都道府県の動的抽出
        df['prefecture'] = df['location'].apply(extract_prefecture)
    
    return df

# Streamlitのページ設定 (プレミアムなデザインを目指す)
st.set_page_config(
    page_title="社内ネットワークエンジニア 求人ダッシュボード",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded"
)

# カスタムCSSの適用
st.markdown("""
<style>
    .reportview-container {
        background: #f8f9fa;
    }
    .job-card {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        margin-bottom: 20px;
        border-left: 5px solid #0066cc;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .job-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0, 0, 0, 0.1);
    }
    .job-card-failed {
        border-left: 5px solid #d9534f;
    }
    .badge {
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 12px;
        font-weight: bold;
        display: inline-block;
        margin-right: 5px;
        margin-bottom: 5px;
    }
    .badge-success {
        background-color: #d4edda;
        color: #155724;
    }
    .badge-danger {
        background-color: #f8d7da;
        color: #721c24;
    }
    .badge-info {
        background-color: #d1ecf1;
        color: #0c5460;
    }
    .badge-warning {
        background-color: #fff3cd;
        color: #856404;
    }
</style>
""", unsafe_allow_html=True)

st.title("🌐 社内ネットワークエンジニア 求人直接収集ダッシュボード")
st.markdown("大手上場企業の公式サイト・採用管理システム（ATS）から直接収集した「社内ネットワーク・正社員・自社勤務」求人の一覧です。")

# データのロード
df = load_data()

if df.empty:
    st.info("求人データがありません。`python run.py` を実行して求人情報を収集してください。")
else:
    # サイドバーフィルター
    st.sidebar.header("🔍 フィルター条件")
    
    # 1. 判定ステータス
    status_filter = st.sidebar.radio(
        "求人抽出",
        ["すべて", "おすすめ（全フィルター通過）", "不適合/要確認のみ"],
        index=1
    )
    
    # 2. 都道府県
    all_prefs = sorted(df['prefecture'].unique())
    selected_prefs = st.sidebar.multiselect(
        "勤務地（都道府県）",
        all_prefs,
        default=all_prefs
    )
    
    # 3. 年間休日
    min_holidays = int(df['holiday_count'].min())
    max_holidays = int(df['holiday_count'].max())
    
    if min_holidays < max_holidays:
        selected_holidays = st.sidebar.slider(
            "最低年間休日数",
            min_value=min_holidays,
            max_value=max_holidays,
            value=min_holidays if min_holidays > 0 else 110
        )
    else:
        selected_holidays = min_holidays

    # 4. キーワード検索
    search_query = st.sidebar.text_input("求人内キーワード検索")
    
    # データフィルタリングの実行
    filtered_df = df.copy()
    
    # ステータスフィルター
    if status_filter == "おすすめ（全フィルター通過）":
        filtered_df = filtered_df[filtered_df['passed_filters']]
    elif status_filter == "不適合/要確認のみ":
        filtered_df = filtered_df[~filtered_df['passed_filters']]
        
    # 都道府県フィルター
    if selected_prefs:
        filtered_df = filtered_df[filtered_df['prefecture'].isin(selected_prefs)]
        
    # 年間休日フィルター
    if min_holidays < max_holidays:
        filtered_df = filtered_df[filtered_df['holiday_count'] >= selected_holidays]
        
    # キーワード検索
    if search_query:
        query = clean_text(search_query)
        # na=False: NULL値を False 扱い、regex=False: 特殊文字を literal 扱い (例: C++, (SE))
        filtered_df = filtered_df[
            filtered_df['title'].str.lower().str.contains(query, na=False, regex=False) |
            filtered_df['description'].str.lower().str.contains(query, na=False, regex=False) |
            filtered_df['company_name'].str.lower().str.contains(query, na=False, regex=False)
        ]
        
    # メイン表示エリアの構築
    # メトリクスの表示
    total_count = len(df)
    filtered_count = len(filtered_df)
    passed_count = len(df[df['passed_filters']])
    
    col1, col2, col3 = st.columns(3)
    col1.metric("総収集件数", f"{total_count} 件")
    col2.metric("おすすめ求人件数", f"{passed_count} 件")
    col3.metric("現在表示中", f"{filtered_count} 件")
    
    st.markdown("---")
    
    # 求人一覧の表示
    if filtered_df.empty:
        st.warning("条件に合致する求人が見つかりませんでした。フィルターを緩めてみてください。")
    else:
        for idx, row in filtered_df.iterrows():
            # カードスタイルクラス
            card_class = "job-card" if row['passed_filters'] else "job-card job-card-failed"
            
            # バッジの作成
            badges_html = ""
            
            # 1. フィルター結果バッジ
            if row['passed_filters']:
                badges_html += '<span class="badge badge-success">✨ おすすめ（適合）</span>'
            else:
                badges_html += '<span class="badge badge-danger">⚠️ 要確認</span>'
                
            # 2. 雇用形態バッジ
            emp = _e(row['employment_type'] if row['employment_type'] else "不明")
            badges_html += f'<span class="badge badge-info">💼 {emp}</span>'
            
            # 3. 年間休日バッジ
            holiday_count = row['holiday_count']
            if holiday_count >= 120:
                badges_html += f'<span class="badge badge-success">📅 年休{holiday_count}日</span>'
            elif holiday_count > 0:
                badges_html += f'<span class="badge badge-warning">📅 年休{holiday_count}日</span>'
            else:
                badges_html += '<span class="badge badge-warning">📅 年休数不明</span>'
                
            # 4. 常駐・派遣バッジ
            if row['is_dispatched']:
                badges_html += '<span class="badge badge-danger">🚫 常駐/派遣の疑いあり</span>'
            else:
                badges_html += '<span class="badge badge-success">🏠 自社勤務（推定）</span>'
                
            # 5. 職種バッジ
            if row['is_network_engineer']:
                badges_html += '<span class="badge badge-success">🌐 NWエンジニア</span>'
            else:
                badges_html += '<span class="badge badge-danger">❓ 非NW職種の疑い</span>'

            # 求人カードの表示（DBデータは全て _e() でエスケープ）
            st.markdown(f"""
            <div class="{card_class}">
                <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                    <div>
                        <h4 style="margin: 0 0 10px 0; color: #333;">{_e(row['company_name'])}</h4>
                        <h3 style="margin: 0 0 10px 0; color: #0066cc;">{_e(row['title'])}</h3>
                    </div>
                    <div style="font-size: 12px; color: #888; text-align: right;">
                        最終更新: {_e(row['updated_at'])}<br>
                        収集日: {_e(row['created_at'])}
                    </div>
                </div>
                <div style="margin-bottom: 15px;">
                    {badges_html}
                </div>
                <p>📍 <strong>勤務地:</strong> {_e(row['location'])}</p>
                <div style="margin-top: 10px;">
                    <a href="{_safe_url(row['job_url'])}" target="_blank" style="
                        background-color: #0066cc;
                        color: white;
                        padding: 8px 16px;
                        text-decoration: none;
                        border-radius: 4px;
                        font-weight: bold;
                        display: inline-block;
                    ">🔗 企業公式求人ページを開く</a>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # 詳細アコーディオン
            with st.expander("📝 職務内容・応募要件の詳細を表示"):
                st.write("**休日詳細テキスト:**")
                st.code(row['holiday_text'] if row['holiday_text'] else "取得不可")
                st.write("**求人票本文:**")
                st.text(row['description'])
            
            st.write("")
