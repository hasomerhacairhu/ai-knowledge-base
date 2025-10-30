#!/usr/bin/env python3
"""Reset stuck files from OOM crash back to SYNCED status."""

import sys
sys.path.insert(0, '/app/src')

from database import DatabaseManager

def reset_stuck_processing():
    """Reset files stuck in PROCESSING status."""
    db = DatabaseManager()
    
    # Get stuck files
    query = """
        SELECT file_id, filename 
        FROM file_state 
        WHERE status = 'PROCESSING'
        ORDER BY updated_at DESC
    """
    
    rows = db.execute_query(query)
    count = len(rows)
    
    if count == 0:
        print("No files stuck in PROCESSING")
        return
    
    print(f"Found {count} files stuck in PROCESSING:")
    for file_id, filename in rows[:10]:
        print(f"  - {filename}")
    if count > 10:
        print(f"  ... and {count - 10} more")
    
    # Reset them
    update_query = """
        UPDATE file_state 
        SET status = 'SYNCED',
            retry_count = 0,
            error_message = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE status = 'PROCESSING'
    """
    
    db.execute_update(update_query)
    print(f"\n✅ Reset {count} files from PROCESSING to SYNCED")

def reset_oom_crashed():
    """Reset files with 'process pool terminated' error."""
    db = DatabaseManager()
    
    # Get OOM crashed files
    query = """
        SELECT file_id, filename 
        FROM file_state 
        WHERE error_message LIKE '%process pool terminated%'
        ORDER BY updated_at DESC
    """
    
    rows = db.execute_query(query)
    count = len(rows)
    
    if count == 0:
        print("\nNo files with 'process pool terminated' error")
        return
    
    print(f"\nFound {count} files with OOM crash error:")
    for file_id, filename in rows[:10]:
        print(f"  - {filename}")
    if count > 10:
        print(f"  ... and {count - 10} more")
    
    # Reset them
    update_query = """
        UPDATE file_state 
        SET status = 'SYNCED',
            retry_count = 0,
            error_message = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE error_message LIKE '%process pool terminated%'
    """
    
    db.execute_update(update_query)
    print(f"✅ Reset {count} files from OOM crash error to SYNCED")

if __name__ == '__main__':
    print("Resetting stuck files from OOM crash...")
    print("=" * 60)
    reset_stuck_processing()
    reset_oom_crashed()
    print("\n" + "=" * 60)
    print("Done!")
