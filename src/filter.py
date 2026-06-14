import re
import jaconv

# 都道府県リスト
PREFECTURES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県",
    "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県",
    "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県",
    "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"
]

def clean_text(text):
    """半角・全角の正規化および小文字化を行います。"""
    if not text:
        return ""
    # 英数字・記号の全角を半角に変換する（kana=False: カタカナは全角のまま保持）
    # キーワード辞書のカタカナは全角で定義しているため、カタカナ変換は行わない
    text = jaconv.zenkaku2hankaku(text, kana=False, digit=True, ascii=True)
    return text.lower().strip()

def parse_holiday_count(text):
    """休日に関するテキストから年間休日数を抽出します。
    
    見つからない場合はNoneを返します。
    """
    if not text:
        return None
    cleaned = clean_text(text)
    
    # パターン1: "年間休日125日" や "年休 120日" など
    patterns = [
        r"(?:年間休日|年休)\s*[:：]?\s*(\d{3})\s*日",
        r"(\d{3})\s*日\s*(?:\(|（)?\s*(?:年間休日|年休)",
        r"(?:年間|年間の)?休日(?:は)?\s*(\d{3})\s*日"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, cleaned)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue
                
    return None

def check_employment_type(emp_text, desc_text=""):
    """雇用形態が正社員であるか判定します。"""
    if not emp_text:
        emp_text = ""
    cleaned_emp = clean_text(emp_text)
    cleaned_desc = clean_text(desc_text)
    
    # 雇用形態項目に「正社員」や「full」が含まれているか
    if "正社員" in cleaned_emp or "full_time" in cleaned_emp or "fulltime" in cleaned_emp:
        return True
        
    # 項目にないが、本文に明記されている場合
    if not cleaned_emp and ("雇用形態:正社員" in cleaned_desc or "雇用形態: 正社員" in cleaned_desc):
        return True
        
    return False

def check_dispatched(title, desc_text):
    """客先常駐・派遣などの求人であるか判定します。
    
    常駐・派遣に該当する場合は True を返します。
    """
    cleaned_title = clean_text(title)
    cleaned_desc = clean_text(desc_text)
    
    # 常駐や派遣、SESを示すキーワード
    exclude_keywords = [
        "客先常駐", "クライアント先", "顧客先", "常駐", "派遣", 
        "ses", "常駐案件", "特定派遣", "アウトソーシング",
        "クライアントオフィス", "顧客オフィス", "常駐型", "配属先企業"
    ]
    
    # タイトルでのマッチ（より強いシグナル）
    for kw in exclude_keywords:
        if kw in cleaned_title:
            return True
            
    # 本文でのマッチ
    # ただし、「常駐しない」「派遣は行わない」などの否定表現を避けるため、
    # 簡易的にキーワードが含まれるかをチェックし、怪しい場合はTrueとする
    for kw in exclude_keywords:
        if kw in cleaned_desc:
            # 「常駐しない」などの文脈か簡易判定
            # 例: "常駐はありません" "常駐なし"
            context_patterns = [
                rf"{kw}(?:はありません|はございません|なし|ゼロ|排除)"
            ]
            is_negated = False
            for pat in context_patterns:
                if re.search(pat, cleaned_desc):
                    is_negated = True
                    break
            if not is_negated:
                return True
                
    return False

def check_network_engineer(title, desc_text):
    """社内ネットワークエンジニアの職種に合致しているか判定します。"""
    cleaned_title = clean_text(title)
    cleaned_desc = clean_text(desc_text)
    
    # ネットワーク関連必須キーワード
    nw_keywords = ["ネットワーク", "network", "nw", "infra", "インフラ"]
    has_nw_keyword = any(kw in cleaned_title or kw in cleaned_desc for kw in nw_keywords)
    if not has_nw_keyword:
        return False
        
    # ネットワークエンジニアの具体的な技術要素
    tech_keywords = [
        "lan", "wan", "vpn", "cisco", "ルーター", "スイッチ", 
        "ファイアウォール", "sd-wan", "fortinet", "juniper", 
        "l2", "l3", "wi-fi", "無線lan", "dns", "dhcp", "load balancer", "ロードバランサ"
    ]
    has_tech = any(tech in cleaned_title or tech in cleaned_desc for tech in tech_keywords)
    
    # 社内（インハウス）エンジニアキーワード
    inhouse_keywords = [
        "社内", "自社", "インハウス", "情報システム", "情シス", 
        "社内se", "コーポレートit", "cit", "社内インフラ"
    ]
    has_inhouse = any(ih in cleaned_title or ih in cleaned_desc for ih in inhouse_keywords)
    
    # 開発（プログラマー）やサーバーインフラ（クラウド専業）を主目的とする求人をある程度フィルタ
    # タイトルに「ソフトウェア開発」「フロントエンド」「バックエンド」「ゲーム開発」などが含まれる場合は除外
    exclude_titles = [
        "フロントエンド", "バックエンド", "アプリ開発", "ゲーム開発", 
        "webデザイナー", "コンテンツ制作", "データサイエンティスト"
    ]
    is_exclude_title = any(ex in cleaned_title for ex in exclude_titles)
    
    # 判定基準: 
    # 1. 除外タイトルではない
    # 2. タイトルに「ネットワーク」または「インフラ」が含まれ、本文に技術要素がある
    # 3. かつ「社内・自社・情報システム」の文脈がある程度確認できること
    is_nw = False
    if not is_exclude_title:
        if ("ネットワーク" in cleaned_title or "nw" in cleaned_title) and (has_tech or has_inhouse):
            is_nw = True
        elif ("インフラ" in cleaned_title or "se" in cleaned_title) and has_tech and has_inhouse:
            is_nw = True
        elif has_tech and has_inhouse and ("ネットワーク" in cleaned_desc or "network" in cleaned_desc):
            is_nw = True
            
    return is_nw

def parse_experience_years(text: str) -> int:
    """求人テキストから必要最低経験年数を抽出します。不明・未経験可は 0 を返します。"""
    if not text:
        return 0
    cleaned = clean_text(text)

    if any(kw in cleaned for kw in ["未経験可", "未経験歓迎", "未経験者歓迎", "未経験ok"]):
        return 0

    patterns = [
        r"実務経験\s*(\d+)\s*年以上",
        r"業務経験\s*(\d+)\s*年以上",
        r"職務経験\s*(\d+)\s*年以上",
        r"経験\s*(\d+)\s*年以上",
        r"(\d+)\s*年以上\s*(?:の)?\s*(?:実務|業務|職務)?経験",
        r"経験年数\s*[:：]?\s*(\d+)\s*年以上",
        r"(\d+)\s*年以上のご?経験",
        r"(\d+)\s*年以上経験(?:者)?",
        r"(\d+)\s*年以上の(?:実務|業務|it|ネットワーク|インフラ|se|システム|エンジニア)",
        r"必須.{0,20}?(\d+)\s*年以上",
        r"(\d+)\s*年以上.{0,10}?(?:必須|required)",
        # 「運用経験（5年以上）」のように経験の後ろにカッコで年数が来るパターン
        r"経験者?\s*\(\s*(\d+)\s*年以上",
        # 「（5年以上）」単体（カッコ内に年数のみ）
        r"\(\s*(\d+)\s*年以上\s*\)",
    ]
    years = []
    for pattern in patterns:
        for m in re.finditer(pattern, cleaned):
            try:
                y = int(m.group(1))
                if 1 <= y <= 20:  # 妥当範囲チェック
                    years.append(y)
            except ValueError:
                pass
    return min(years) if years else 0


def extract_prefecture(location_text):
    """勤務地テキストから都道府県を抽出します。"""
    if not location_text:
        return "未定/不明"
    
    cleaned = clean_text(location_text)
    for pref in PREFECTURES:
        if pref in cleaned or pref.replace("都", "").replace("府", "").replace("県", "") in cleaned:
            return pref
            
    return "その他"

def evaluate_job(job):
    """求人データにフィルターを適用し、判定結果を求人辞書に追加します。
    
    job辞書に必要なフィールド:
        - company_name
        - title
        - employment_type
        - holiday_text
        - location
        - description
    """
    # 1. 雇用形態判定
    is_regular = check_employment_type(job.get('employment_type', ''), job.get('description', ''))
    
    # 2. 年間休日判定
    holiday_count = parse_holiday_count(job.get('holiday_text', ''))
    if holiday_count is None:
        holiday_count = parse_holiday_count(job.get('description', ''))
        
    is_holiday_ok = False
    if holiday_count is not None:
        is_holiday_ok = (holiday_count >= 120)
    else:
        # 休日数が抽出できない場合のフォールバック
        # 「完全週休2日」かつ「祝日」などの文脈があれば120日以上と推定
        desc_cleaned = clean_text(job.get('description', ''))
        holiday_cleaned = clean_text(job.get('holiday_text', ''))
        full_text = desc_cleaned + " " + holiday_cleaned
        if "完全週休2日" in full_text and ("祝" in full_text or "土日祝" in full_text):
            is_holiday_ok = True
            holiday_count = 120  # 推定値
            
    # 3. 客先常駐判定 (True なら常駐・派遣)
    is_dispatched = check_dispatched(job.get('title', ''), job.get('description', ''))
    
    # 4. 職種（ネットワークエンジニア）判定
    is_network = check_network_engineer(job.get('title', ''), job.get('description', ''))
    
    # 都道府県抽出
    pref = extract_prefecture(job.get('location', ''))
    
    # 総合判定 (正社員 ＆ 休日120日以上 ＆ 常駐でない ＆ ネットワークエンジニア)
    passed_filters = is_regular and is_holiday_ok and (not is_dispatched) and is_network
    
    # 結果の格納
    job['holiday_count'] = holiday_count if holiday_count is not None else 0
    job['is_network_engineer'] = is_network
    job['is_dispatched'] = is_dispatched
    job['passed_filters'] = passed_filters
    job['extracted_prefecture'] = pref
    
    return job
