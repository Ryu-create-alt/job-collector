import sqlite3
import os
from datetime import datetime

def init_db(db_path="jobs.db"):
    """データベースとテーブルを初期化します。"""
    # ディレクトリが存在しない場合は作成
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # jobs テーブルの作成
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                title TEXT NOT NULL,
                job_url TEXT,
                employment_type TEXT,
                holiday_text TEXT,
                holiday_count INTEGER,
                location TEXT,
                description TEXT,
                is_network_engineer INTEGER, -- 0 or 1
                is_dispatched INTEGER,       -- 0 or 1
                passed_filters INTEGER,      -- 0 or 1
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(company_name, title)  -- 重複排除のユニークキー
            )
        """)

def save_jobs(jobs_list, db_path="jobs.db"):
    """求人データのリストをデータベースに保存（UPSERT）します。
    
    jobs_list の要素は辞書:
    {
        'company_name': str,
        'title': str,
        'job_url': str,
        'employment_type': str,
        'holiday_text': str,
        'holiday_count': int,
        'location': str,
        'description': str,
        'is_network_engineer': bool,
        'is_dispatched': bool,
        'passed_filters': bool
    }
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    inserted_count = 0
    updated_count = 0

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        for job in jobs_list:
            # 重複があるか確認
            cursor.execute(
                "SELECT id FROM jobs WHERE company_name = ? AND title = ?",
                (job['company_name'], job['title'])
            )
            row = cursor.fetchone()

            is_net = 1 if job.get('is_network_engineer', False) else 0
            is_disp = 1 if job.get('is_dispatched', False) else 0
            passed = 1 if job.get('passed_filters', False) else 0

            if row is None:
                # 新規挿入
                cursor.execute("""
                    INSERT INTO jobs (
                        company_name, title, job_url, employment_type,
                        holiday_text, holiday_count, location, description,
                        is_network_engineer, is_dispatched, passed_filters,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    job['company_name'],
                    job['title'],
                    job.get('job_url', ''),
                    job.get('employment_type', ''),
                    job.get('holiday_text', ''),
                    job.get('holiday_count', 0),
                    job.get('location', ''),
                    job.get('description', ''),
                    is_net,
                    is_disp,
                    passed,
                    now_str,
                    now_str
                ))
                inserted_count += 1
            else:
                # 既存更新 (created_at はそのまま、updated_at を更新)
                job_id = row[0]
                cursor.execute("""
                    UPDATE jobs SET
                        job_url = ?,
                        employment_type = ?,
                        holiday_text = ?,
                        holiday_count = ?,
                        location = ?,
                        description = ?,
                        is_network_engineer = ?,
                        is_dispatched = ?,
                        passed_filters = ?,
                        updated_at = ?
                    WHERE id = ?
                """, (
                    job.get('job_url', ''),
                    job.get('employment_type', ''),
                    job.get('holiday_text', ''),
                    job.get('holiday_count', 0),
                    job.get('location', ''),
                    job.get('description', ''),
                    is_net,
                    is_disp,
                    passed,
                    now_str,
                    job_id
                ))
                updated_count += 1

    return inserted_count, updated_count

def get_all_jobs(db_path="jobs.db"):
    """データベースからすべての求人データを取得します。"""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM jobs ORDER BY updated_at DESC")
        rows = cursor.fetchall()

        jobs_list = []
        for row in rows:
            job = dict(row)
            # booleanの型変換
            job['is_network_engineer'] = bool(job['is_network_engineer'])
            job['is_dispatched'] = bool(job['is_dispatched'])
            job['passed_filters'] = bool(job['passed_filters'])
            jobs_list.append(job)

    return jobs_list
