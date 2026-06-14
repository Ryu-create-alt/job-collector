import json
import os
import re
import time

from src.filter import evaluate_job

_PROMPT_TEMPLATE = """
{company_name} で現在募集中の「社内ネットワークエンジニア（正社員）」の求人を調べてください。

条件：
- 雇用形態が正社員であること
- 勤務場所が自社オフィス・本社（客先常駐・出向・常駐派遣ではない）
- 対象職種：社内LAN/WAN/VPN/ファイアウォール等の設計・構築・運用・保守

以下のJSON形式のみで返してください（説明文・マークダウン装飾は不要）:
{{
  "found": true,
  "jobs": [
    {{
      "title": "求人タイトル",
      "employment_type": "正社員",
      "holiday_text": "年間休日125日（土日祝）など休日に関する記述。不明なら空文字",
      "location": "勤務地（例: 東京都千代田区）。不明なら空文字",
      "job_url": "求人ページのURL。不明なら空文字",
      "description": "職務内容の概要（200字程度）"
    }}
  ]
}}

求人が見つからない・募集していない場合: {{"found": false, "jobs": []}}
"""


def _strip_markdown(text: str) -> str:
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```", "", text)
    return text.strip()


_RETRY_DELAYS = [10, 30, 60]  # 503時のリトライ間隔（秒）


def _collect_for_company(client, company: dict) -> list[dict]:
    """1社分の求人を Gemini API で取得し、フィルタ評価済みのリストを返す。503時はリトライ。"""
    from google.genai import types

    company_name = company["company_name"]
    prompt = _PROMPT_TEMPLATE.format(company_name=company_name)

    for attempt, delay in enumerate([0] + _RETRY_DELAYS, start=1):
        if delay:
            print(f"  [RETRY {attempt}/4] {delay}秒後に再試行...")
            time.sleep(delay)
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                ),
            )
            data = json.loads(_strip_markdown(response.text))
            break
        except json.JSONDecodeError as e:
            print(f"  [WARN] {company_name}: JSONパース失敗 - {e}")
            return []
        except Exception as e:
            err = str(e)
            if "503" in err and attempt <= len(_RETRY_DELAYS):
                print(f"  [503] {company_name}: 一時的な高負荷")
                continue
            print(f"  [ERROR] {company_name}: {e}")
            return []
    else:
        print(f"  [SKIP] {company_name}: リトライ上限に達しました")
        return []

    if not data.get("found"):
        return []

    jobs = []
    for job in data.get("jobs", []):
        job["company_name"] = company_name
        jobs.append(evaluate_job(job))
    return jobs


def run_collector(companies: list[dict], progress_callback=None) -> list[dict]:
    """全企業の求人を Gemini API で収集して返す。"""
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY が設定されていません。.env を確認してください。")

    client = genai.Client(api_key=api_key)
    all_jobs = []
    total = len(companies)

    for idx, company in enumerate(companies):
        company_name = company["company_name"]
        if progress_callback:
            progress_callback(f"[{idx + 1}/{total}] {company_name} を検索中...")
        print(f"Collecting [{idx + 1}/{total}]: {company_name}")

        jobs = _collect_for_company(client, company)
        passed = sum(1 for j in jobs if j["passed_filters"])
        print(f"  -> {len(jobs)} 件取得（フィルター通過: {passed} 件）")
        all_jobs.extend(jobs)

        # APIレート制限対策（企業間ディレイ）
        if idx < total - 1:
            time.sleep(2)

    return all_jobs
