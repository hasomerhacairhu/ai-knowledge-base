#!/usr/bin/env python3
"""
Error Discovery Script
Analyzes errors in the file_state table to identify common patterns and issues.
"""

import os
import sys
from collections import Counter
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import RealDictCursor


def get_db_connection():
    """Create database connection."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "ai_knowledge_base"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
    )


def analyze_errors(hours=24, limit=50):
    """Analyze errors from the database."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    print("=" * 80)
    print("🔍 ERROR ANALYSIS REPORT")
    print("=" * 80)
    print()
    
    # Overall status distribution
    print("📊 OVERALL STATUS DISTRIBUTION")
    print("-" * 80)
    cur.execute("""
        SELECT status, COUNT(*) as count
        FROM file_state
        GROUP BY status
        ORDER BY count DESC
    """)
    for row in cur.fetchall():
        print(f"  {row['status']:20s}: {row['count']:,}")
    print()
    
    # Recent errors (last N hours)
    print(f"⏰ ERRORS IN LAST {hours} HOURS")
    print("-" * 80)
    cur.execute("""
        SELECT COUNT(*) as count
        FROM file_state
        WHERE status = 'failed_process'
        AND updated_at > NOW() - INTERVAL '%s hours'
    """, (hours,))
    recent_count = cur.fetchone()['count']
    print(f"  Total recent errors: {recent_count}")
    print()
    
    # Error patterns
    print("🔥 TOP ERROR PATTERNS")
    print("-" * 80)
    cur.execute("""
        SELECT 
            CASE 
                WHEN error_message LIKE '%partition_epub%' THEN 'EPUB: Missing dependencies'
                WHEN error_message LIKE '%timeout%' THEN 'Timeout'
                WHEN error_message LIKE '%S3%' OR error_message LIKE '%download%' THEN 'S3/Download issue'
                WHEN error_message LIKE '%OCR%' OR error_message LIKE '%tesseract%' THEN 'OCR/Tesseract issue'
                WHEN error_message LIKE '%memory%' OR error_message LIKE '%MemoryError%' THEN 'Memory issue'
                WHEN error_message LIKE '%PDF%' AND error_message LIKE '%encrypted%' THEN 'PDF: Encrypted'
                WHEN error_message LIKE '%PDF%' AND error_message LIKE '%password%' THEN 'PDF: Password protected'
                WHEN error_message LIKE '%PDF%' THEN 'PDF: Other issue'
                WHEN error_message LIKE '%permission%' OR error_message LIKE '%access%' THEN 'Permission denied'
                WHEN error_message IS NULL THEN 'No error message'
                ELSE 'Other'
            END as error_category,
            COUNT(*) as count
        FROM file_state
        WHERE status = 'failed_process'
        GROUP BY error_category
        ORDER BY count DESC
    """)
    
    for row in cur.fetchall():
        category = row['error_category']
        count = row['count']
        print(f"  {category:40s}: {count:,}")
    print()
    
    # Most common exact errors
    print(f"📝 TOP {min(limit, 10)} EXACT ERROR MESSAGES")
    print("-" * 80)
    cur.execute("""
        SELECT 
            LEFT(error_message, 150) as short_error,
            COUNT(*) as count
        FROM file_state
        WHERE status = 'failed_process'
        AND error_message IS NOT NULL
        GROUP BY error_message
        ORDER BY count DESC
        LIMIT %s
    """, (min(limit, 10),))
    
    for i, row in enumerate(cur.fetchall(), 1):
        print(f"\n  {i}. Count: {row['count']}")
        print(f"     {row['short_error']}")
    print()
    
    # Recent failures with file info
    print(f"📄 RECENT {min(limit, 20)} FAILED FILES")
    print("-" * 80)
    cur.execute("""
        SELECT 
            drive_path,
            LEFT(error_message, 100) as short_error,
            updated_at
        FROM file_state
        WHERE status = 'failed_process'
        ORDER BY updated_at DESC
        LIMIT %s
    """, (min(limit, 20),))
    
    for i, row in enumerate(cur.fetchall(), 1):
        time_str = row['updated_at'].strftime('%Y-%m-%d %H:%M:%S') if row['updated_at'] else 'Unknown'
        print(f"\n  {i}. {time_str}")
        print(f"     File: {row['drive_path']}")
        print(f"     Error: {row['short_error']}")
    print()
    
    # File type breakdown of errors
    print("📋 ERROR BREAKDOWN BY FILE TYPE")
    print("-" * 80)
    cur.execute("""
        SELECT 
            CASE 
                WHEN drive_path LIKE '%.pdf' THEN 'PDF'
                WHEN drive_path LIKE '%.docx' THEN 'DOCX'
                WHEN drive_path LIKE '%.doc' THEN 'DOC'
                WHEN drive_path LIKE '%.pptx' THEN 'PPTX'
                WHEN drive_path LIKE '%.ppt' THEN 'PPT'
                WHEN drive_path LIKE '%.epub' THEN 'EPUB'
                WHEN drive_path LIKE '%.txt' THEN 'TXT'
                ELSE 'Other'
            END as file_type,
            COUNT(*) as count
        FROM file_state
        WHERE status = 'failed_process'
        GROUP BY file_type
        ORDER BY count DESC
    """)
    
    for row in cur.fetchall():
        print(f"  {row['file_type']:10s}: {row['count']:,}")
    print()
    
    print("=" * 80)
    
    cur.close()
    conn.close()


if __name__ == "__main__":
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    
    try:
        analyze_errors(hours, limit)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
