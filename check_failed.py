#!/usr/bin/env python3
"""Check failed files"""
from src.database import Database
from src.config import Config

config = Config.from_env()

db = Database(
    host=config.postgres_host,
    port=config.postgres_port,
    database=config.postgres_db,
    user=config.postgres_user,
    password=config.postgres_password
)

with db.get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT original_name, status, error_message, retry_count, original_file_size, updated_at
            FROM file_state 
            WHERE status LIKE 'FAILED%' OR (error_message IS NOT NULL AND error_message != '')
            ORDER BY updated_at DESC 
            LIMIT 5
        """)
        rows = cur.fetchall()
        
        if not rows:
            print('No failed or error files found')
        else:
            for i, row in enumerate(rows, 1):
                print(f"{i}. {row[0]}")
                print(f"   Error: {row[2][:300] if row[2] else None}")
                print(f"   Retry: {row[3]}, Size: {row[4]:,}, Updated: {row[5]}")
                print()
