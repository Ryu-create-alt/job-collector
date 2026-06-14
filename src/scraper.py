import time
import json
import re
import urllib.robotparser
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from src.filter import evaluate_job

# 個人ツールであることを明示するUser-Agent
_USER_AGENT = "JobCollector/1.0 (personal-use; contact: private)"

def _is_allowed_by_robots(base_url: str) -> bool:
    """robots.txt を確認し、アクセス可否を返す。取得失敗時はアクセス許可として扱う。"""
    try:
        parsed = urlparse(base_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(_USER_AGENT, base_url)
    except Exception:
        return True

def extract_json_ld(html):
    """HTMLから Schema.org/JobPosting 構造化データを抽出します。"""
    soup = BeautifulSoup(html, 'html.parser')
    json_ld_tags = soup.find_all('script', type='application/ld+json')
    for tag in json_ld_tags:
        try:
            if not tag.string:
                continue
            data = json.loads(tag.string)
            if isinstance(data, dict):
                if data.get('@type') == 'JobPosting':
                    return data
                # グラフ構造などの入れ子対応
                if '@graph' in data:
                    for item in data['@graph']:
                        if item.get('@type') == 'JobPosting':
                            return item
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get('@type') == 'JobPosting':
                        return item
        except Exception:
            continue
    return None

def parse_job_from_json_ld(json_ld, url, company_name):
    """JSON-LDデータから求人辞書を構築します。"""
    title = json_ld.get('title', '')
    desc = json_ld.get('description', '')
    
    # 雇用形態の抽出と日本語変換
    emp_type_raw = json_ld.get('employmentType', '')
    if isinstance(emp_type_raw, list):
        # リスト先頭の値を代表値として使用（複数形態の場合は先頭を優先）
        emp_type_raw = emp_type_raw[0] if emp_type_raw else ''
    emp_type_map = {
        "FULL_TIME": "正社員",
        "PART_TIME": "アルバイト/パート",
        "CONTRACTOR": "契約社員",
        "TEMPORARY": "派遣",
        "INTERN": "インターン",
        "VOLUNTEER": "ボランティア",
        "PER_DIEM": "日雇い",
        "OTHER": "その他",
    }
    emp_type = emp_type_map.get(emp_type_raw.upper(), emp_type_raw)
        
    # 勤務地の抽出
    location = ""
    loc_data = json_ld.get('jobLocation', {})
    if isinstance(loc_data, dict):
        address = loc_data.get('address', {})
        if isinstance(address, dict):
            region = address.get('addressRegion', '')
            locality = address.get('addressLocality', '')
            street = address.get('streetAddress', '')
            location = f"{region}{locality}{street}".strip()
        elif isinstance(address, str):
            location = address
            
    # JSON-LDに勤務地がない場合のフォールバック（テキストパース）
    if not location:
        location = "求人票を参照"

    # HTMLタグを除去したプレーンテキストの説明文
    soup = BeautifulSoup(desc, 'html.parser')
    plain_desc = soup.get_text(separator=' ').strip()
    
    # 休日情報の抽出
    # description内の「休日」を含む部分から簡易的に取得
    holiday_text = ""
    for line in plain_desc.split('\n'):
        if '休日' in line or '休暇' in line or '年休' in line:
            holiday_text += line + "\n"

    return {
        'company_name': company_name,
        'title': title,
        'job_url': url,
        'employment_type': emp_type,
        'holiday_text': holiday_text.strip(),
        'location': location,
        'description': plain_desc
    }

def get_job_urls(page, base_url, ats_type):
    """採用一覧ページから求人詳細ページのURL一覧を抽出します。"""
    urls = set()
    page.goto(base_url)
    
    # SPAのレンダリング待機
    page.wait_for_timeout(3000)
    
    # 全リンクの取得
    hrefs = page.evaluate("() => Array.from(document.querySelectorAll('a')).map(a => a.href)")
    
    # ATSタイプ別のURL判定パターン
    if ats_type == 'hrmos':
        # 例: https://hrmos.co/pages/visional/jobs/123456789
        pattern = re.compile(r'/jobs/\d+')
        for href in hrefs:
            if pattern.search(href):
                urls.add(href)
    elif ats_type == 'herp':
        # 例: https://jobs.herp.careers/smarthr/receptions/1234-abcd
        pattern = re.compile(r'/receptions/[a-zA-Z0-9_-]+')
        for href in hrefs:
            if pattern.search(href) and not href.endswith('/receptions'):
                urls.add(href)
    else:
        # 一般の独自サイト: 「jobs」「careers」「detail」などのキーワードを含むリンク
        # かつドメインが同じものを優先
        parsed_base = urlparse(base_url)
        for href in hrefs:
            if not href:
                continue
            parsed_href = urlparse(href)
            # 同じドメイン内であること
            if parsed_href.netloc == parsed_base.netloc:
                if any(x in href.lower() for x in ['/job', '/career', '/detail', '/recruit']):
                    # 一覧ページそのものは除く
                    if not any(x == href.lower().rstrip('/') for x in [base_url.lower().rstrip('/'), base_url.lower()]):
                        urls.add(href)
                        
    return list(urls)

def scrape_job_detail(page, url, company_name):
    """求人詳細ページを巡回し、情報を抽出します。"""
    try:
        page.goto(url)
        page.wait_for_timeout(2000) # 念のため待機
        
        html = page.content()
        json_ld = extract_json_ld(html)
        
        if json_ld:
            # JSON-LD から高精度にパース
            return parse_job_from_json_ld(json_ld, url, company_name)
        else:
            # フォールバック: HTMLのテキスト解析
            soup = BeautifulSoup(html, 'html.parser')
            title = page.title()
            # 求人タイトルらしいものをh1などから探す
            h1 = soup.find('h1')
            if h1:
                title = h1.get_text().strip()
                
            body_text = soup.get_text(separator=' ')
            
            # 休日情報や勤務地をヒューリスティックに抽出
            holiday_text = ""
            location = ""
            employment_type = "正社員" # デフォルト
            
            lines = [line.strip() for line in body_text.split('\n') if line.strip()]
            for i, line in enumerate(lines):
                if '勤務地' in line or '仕事場所' in line:
                    location = line
                    if len(location) < 15 and i + 1 < len(lines):
                        location += " " + lines[i+1]
                if '休日' in line or '休暇' in line or '年休' in line:
                    holiday_text += line + "\n"
                if '雇用形態' in line:
                    employment_type = line
                    if len(employment_type) < 15 and i + 1 < len(lines):
                        employment_type += " " + lines[i+1]
                        
            return {
                'company_name': company_name,
                'title': title,
                'job_url': url,
                'employment_type': employment_type,
                'holiday_text': holiday_text.strip(),
                'location': location or "求人票を参照",
                'description': body_text
            }
    except Exception as e:
        print(f"Error scraping detail page {url}: {e}")
        return None

def run_scraper(companies, progress_callback=None):
    """スクレイパーを実行し、求人リストを取得してフィルタリングします。"""
    all_jobs = []
    
    with sync_playwright() as p:
        # ヘッドレスブラウザを起動
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(user_agent=_USER_AGENT)
            try:
                page = context.new_page()

                for idx, company in enumerate(companies):
                    company_name = company['company_name']
                    url = company['url']
                    ats_type = company['ats_type']

                    if progress_callback:
                        progress_callback(f"{company_name} ({ats_type}) の求人一覧を収集中...")

                    print(f"Scraping list for {company_name}: {url}")
                    try:
                        if not _is_allowed_by_robots(url):
                            print(f"  [SKIP] robots.txt によりアクセス禁止: {url}")
                            continue
                        job_urls = get_job_urls(page, url, ats_type)
                        print(f"Found {len(job_urls)} job URLs for {company_name}")

                        # 詳細ページの巡回
                        for detail_url in job_urls[:10]: # プロトタイプなので各社最大10件に制限
                            if progress_callback:
                                progress_callback(f"  -> {company_name} の詳細ページをスクレイプ中: {detail_url}")

                            print(f"Scraping detail: {detail_url}")
                            job_data = scrape_job_detail(page, detail_url, company_name)

                            if job_data:
                                # フィルタ評価の適用
                                evaluated_job = evaluate_job(job_data)
                                all_jobs.append(evaluated_job)
                                print(f"  Job parsed: {evaluated_job['title']} (Passed filter: {evaluated_job['passed_filters']})")

                            # 相手サーバー負荷軽減のためディレイ
                            time.sleep(3)

                    except Exception as e:
                        print(f"Error scraping {company_name}: {e}")

                    # 企業間のアクセスディレイ（サーバー負荷軽減）
                    if idx < len(companies) - 1:
                        time.sleep(3)
            finally:
                context.close()
        finally:
            browser.close()

    return all_jobs
