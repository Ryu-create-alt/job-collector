import argparse
import json
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv, find_dotenv

from src.database import init_db, save_jobs
from src.gemini_collector import run_collector

load_dotenv(find_dotenv())

_BASE_DIR = Path(__file__).parent
_DB_PATH = str(_BASE_DIR / "jobs.db")
_CONFIG_PATH = _BASE_DIR / "config" / "companies.json"
_PROGRESS_PATH = _BASE_DIR / "config" / "progress.json"


def _load_progress() -> int:
    if _PROGRESS_PATH.exists():
        with open(_PROGRESS_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("last_index", 0)
    return 0


def _save_progress(last_index: int):
    with open(_PROGRESS_PATH, "w", encoding="utf-8") as f:
        json.dump({"last_index": last_index}, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="社内NWエンジニア求人収集")
    parser.add_argument(
        "--batch-size", type=int, default=10,
        metavar="N", help="1回の実行で取得する企業数（デフォルト: 10）"
    )
    args = parser.parse_args()

    print("=" * 52)
    print("[-] 社内NWエンジニア求人収集")
    print("=" * 52)

    # 1. DB初期化
    init_db(_DB_PATH)

    # 2. 企業リスト読み込み
    if not _CONFIG_PATH.exists():
        print("[!] config/companies.json が見つかりません。")
        print("    先に以下を実行してください:")
        print("      python update_companies.py")
        sys.exit(1)

    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        companies = json.load(f)

    total = len(companies)

    # 3. 進捗読み込み・今回の対象範囲を決定
    start = _load_progress()

    if start >= total:
        print(f"[*] 全 {total} 社の取得が完了しています。")
        print("[*] 新しい企業リストを追記取得します...")
        result = subprocess.run(
            [sys.executable, str(_BASE_DIR / "update_companies.py"), "--append"],
            check=False
        )
        if result.returncode != 0:
            print("[!] 企業リスト追記に失敗しました。時間をおいて再実行してください。")
            sys.exit(1)
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            companies = json.load(f)
        total = len(companies)
        start = _load_progress()

    end = min(start + args.batch_size, total)
    batch = companies[start:end]

    print(f"[*] 企業リスト: 全 {total} 社")
    print(f"[*] 今回の対象: {start + 1}〜{end} 社目（{len(batch)} 社）")
    print()

    # 4. Gemini API で求人収集
    def log_progress(msg):
        print(f"  {msg}")

    all_jobs = run_collector(batch, progress_callback=log_progress)

    print(f"\n[*] 収集完了。取得件数: {len(all_jobs)} 件")

    # 5. DB保存
    if all_jobs:
        inserted, updated = save_jobs(all_jobs, _DB_PATH)
        passed = sum(1 for j in all_jobs if j["passed_filters"])
        print(f"[*] 新規登録: {inserted} 件 / 更新: {updated} 件 / フィルター通過: {passed} 件")
    else:
        print("[*] 今回は求人が見つかりませんでした。")

    # 6. 進捗保存
    _save_progress(end)
    remaining = total - end
    print()
    print("=" * 52)
    if end >= total:
        print(f"[-] 全 {total} 社の取得完了！")
        print("    次回実行時に新しい企業リストを自動追記します。")
    else:
        print(f"[-] 本日分完了（{end}/{total} 社）")
        print(f"    残り {remaining} 社 — 明日以降に続きを取得します。")
    print()
    print("   ダッシュボード: streamlit run src/dashboard.py")
    print("=" * 52)


if __name__ == "__main__":
    main()
