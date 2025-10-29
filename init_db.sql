-- AI Knowledge Base PostgreSQL Schema
-- This schema is automatically created by the Database class in src/database.py
-- This file is provided for reference and manual migration purposes only

-- Main file state table
CREATE TABLE IF NOT EXISTS file_state (
    sha256 TEXT PRIMARY KEY,
    drive_file_id TEXT,
    drive_path TEXT,
    original_name TEXT,
    s3_key TEXT NOT NULL,
    extension TEXT,
    status TEXT NOT NULL,
    
    -- Stage timestamps
    synced_at TIMESTAMP,
    processed_at TIMESTAMP,
    indexed_at TIMESTAMP,
    
    -- Drive metadata
    drive_created_time TIMESTAMP,
    drive_modified_time TIMESTAMP,
    drive_mime_type TEXT,
    
    -- OpenAI references
    openai_file_id TEXT,
    vector_store_id TEXT,
    
    -- Error tracking
    error_message TEXT,
    error_type TEXT,
    retry_count INTEGER DEFAULT 0,
    last_error_at TIMESTAMP,
    
    -- Metadata
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_status 
ON file_state(status);

CREATE INDEX IF NOT EXISTS idx_drive_file_id 
ON file_state(drive_file_id);

CREATE INDEX IF NOT EXISTS idx_updated_at 
ON file_state(updated_at);

-- Drive file mapping table - tracks all Drive files pointing to same SHA256
CREATE TABLE IF NOT EXISTS drive_file_mapping (
    drive_file_id TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    drive_path TEXT,
    original_name TEXT,
    drive_created_time TIMESTAMP,
    drive_modified_time TIMESTAMP,
    drive_mime_type TEXT,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (sha256) REFERENCES file_state(sha256)
);

CREATE INDEX IF NOT EXISTS idx_drive_mapping_sha256
ON drive_file_mapping(sha256);

-- Checkpoint table for incremental sync
CREATE TABLE IF NOT EXISTS checkpoint (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

-- Status values reference:
-- - synced: Downloaded from Drive to S3 objects/
-- - processing: Being processed by Unstructured
-- - processed: Processing complete, derivatives/ created
-- - indexing: Being indexed to Vector Store
-- - indexed: Successfully indexed to Vector Store
-- - failed_sync: Failed during sync
-- - failed_process: Failed during processing
-- - failed_index: Failed during indexing
