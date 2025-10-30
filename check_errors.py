#!/usr/bin/env python3
"""Check failed files grouped by error type"""
from src.database import Database
from src.config import Config
from collections import Counter

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
            SELECT error_message, COUNT(*) as count
            FROM file_state 
            WHERE status LIKE 'FAILED%' OR (error_message IS NOT NULL AND error_message != '')
            GROUP BY error_message
            ORDER BY count DESC
        """)
        rows = cur.fetchall()
        
        if not rows:
            print('No failed or error files found')
        else:
            print(f"Failed files by error type ({len(rows)} unique errors):\n")
            total = 0
            for error_msg, count in rows:
                total += count
                print(f"{count:4d} files: {error_msg[:150]}")
            print(f"\n{'='*80}")
            print(f"Total failed: {total} files")
