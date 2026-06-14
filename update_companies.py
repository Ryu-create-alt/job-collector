import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

_BASE_DIR = Path(__file__).parent
_CONFIG_PATH = _BASE_DIR / "config" / "companies.json"
_PROGRESS_PATH = _BASE_DIR / "config" / "progress.json"

_PROMPT_NEW = """
東証プライムまたはスタンダードに上場している日本企業の中から、
「社内ネットワークエンジニア（情報システム部門所属・自社LAN/WAN/VPN等の設計・運用・保守を担う正社員ポジション）」
を採用する可能性が高い企業を100社リストアップしてください。

選定基準：
- 東証プライムまたはスタンダード上場企業
- 情報システム部門の規模が大きい業界（金融・銀行・保険・製造・流通・小売・メディア・通信・インフラ・物流・医療・不動産・ゲーム・エンタメ等）
- 自社のネットワークインフラを内製（インハウス）で運用している企業
- SIer・人材派遣・SES企業は除く

以下のJSON配列のみを出力してください（説明文・マークダウン装飾は不要）:
[
  {{"company_name": "株式会社○○", "industry": "金融"}},
  {{"company_name": "株式会社△△", "industry": "製造"}}
]
"""

_PROMPT_APPEND = """
東証プライムまたはスタンダードに上場している日本企業の中から、
「社内ネットワークエンジニア（情報システム部門所属・自社LAN/WAN/VPN等の設計・運用・保守を担う正社員ポジション）」
を採用する可能性が高い企業を100社リストアップしてください。

選定基準：
- 東証プライムまたはスタンダード上場企業
- 情報システム部門の規模が大きい業界（金融・銀行・保険・製造・流通・小売・メディア・通信・インフラ・物流・医療・不動産・ゲーム・エンタメ・航空・食品・化学・薬品・建設等）
- 自社のネットワークインフラを内製（インハウス）で運用している企業
- SIer・人材派遣・SES企業は除く

以下の企業はすでにリスト済みのため除外してください：
{existing_names}

上記以外から100社を選び、以下のJSON配列のみを出力してください（説明文・マークダウン装飾は不要）:
[
  {{"company_name": "株式会社○○", "industry": "金融"}},
  {{"company_name": "株式会社△△", "industry": "製造"}}
]
"""


def _strip_markdown(text: str) -> str:
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```", "", text)
    return text.strip()


def _call_gemini(prompt: str) -> list[dict]:
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY が設定されていません。.env を確認してください。")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        ),
    )
    return json.loads(_strip_markdown(response.text))


def _fetch_with_retry(prompt: str) -> list[dict] | None:
    for attempt in range(1, 4):
        try:
            return _call_gemini(prompt)
        except Exception as e:
            print(f"[!] 試行 {attempt}/3 失敗: {e}")
            if attempt < 3:
                print("    30秒後に再試行します...")
                time.sleep(30)
    return None


def main():
    parser = argparse.ArgumentParser(description="対象企業リストの取得・追記")
    parser.add_argument(
        "--append", action="store_true",
        help="既存リストに新しい企業を追記する（全社取得完了後に使用）"
    )
    args = parser.parse_args()

    if args.append:
        # 追記モード
        print("=" * 52)
        print("[-] 企業リスト追記（新規100社を追加）")
        print("=" * 52)

        if not _CONFIG_PATH.exists():
            print("[!] companies.json が見つかりません。--append なしで先に実行してください。")
            sys.exit(1)

        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            existing = json.load(f)

        existing_names = "\n".join(f"- {c['company_name']}" for c in existing)
        prompt = _PROMPT_APPEND.format(existing_names=existing_names)

        print(f"[*] 既存: {len(existing)} 社。新規100社を取得中...")
        new_companies = _fetch_with_retry(prompt)
        if new_companies is None:
            print("[!] 取得できませんでした。時間をおいて再実行してください。")
            sys.exit(1)

        # 重複除去して追記
        existing_set = {c["company_name"] for c in existing}
        added = [c for c in new_companies if c["company_name"] not in existing_set]
        merged = existing + added

        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)

        # 進捗リセット（追記分の先頭から再開）
        with open(_PROGRESS_PATH, "w", encoding="utf-8") as f:
            json.dump({"last_index": len(existing)}, f, indent=2)

        print(f"[OK] {added} 社を追記しました（合計 {len(merged)} 社）。")
        print(f"     次回の run.py は {len(existing) + 1} 社目から再開します。")

    else:
        # 新規作成モード
        print("=" * 52)
        print("[-] 対象企業リスト新規取得（月1回・手動実行）")
        print("=" * 52)

        print("[*] Gemini API で企業リストを取得中（数十秒かかります）...")
        companies = _fetch_with_retry(_PROMPT_NEW)
        if companies is None:
            print("[!] 3回試行しても取得できませんでした。時間をおいて再実行してください。")
            sys.exit(1)

        print(f"[*] {len(companies)} 社を取得しました。")

        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(companies, f, ensure_ascii=False, indent=2)

        # 進捗リセット
        with open(_PROGRESS_PATH, "w", encoding="utf-8") as f:
            json.dump({"last_index": 0}, f, indent=2)

        print(f"[OK] {_CONFIG_PATH} を更新しました。")
        print("     python run.py --batch-size 10 で毎日少しずつ収集できます。")

    print("=" * 52)


if __name__ == "__main__":
    main()
