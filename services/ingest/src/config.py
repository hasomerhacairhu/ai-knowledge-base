"""Configuration management for the ingest pipeline"""

import os
from dataclasses import dataclass
from typing import List
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Configuration for the ingest pipeline"""
    
    # Google Drive
    google_service_account_file: str
    google_drive_folder_id: str
    
    # S3 Storage
    s3_endpoint: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str
    s3_region: str
    
    # OpenAI
    openai_api_key: str
    vector_store_id: str
    
    # Processing
    max_files_per_run: int
    additional_extensions: List[str]  # Non-Google Workspace file extensions (e.g., .pdf, .docx)
    
    # Concurrency
    processor_max_workers: int
    indexer_max_workers: int
    
    # Processing Engine
    processing_engine: str  # "unstructured" or "docling"
    
    # Database (PostgreSQL)
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    
    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables"""
        
        # Required fields
        required = {
            "GOOGLE_SERVICE_ACCOUNT_FILE": os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE"),
            "GOOGLE_DRIVE_FOLDER_ID": os.getenv("GOOGLE_DRIVE_FOLDER_ID"),
            "S3_ENDPOINT": os.getenv("S3_ENDPOINT"),
            "S3_ACCESS_KEY": os.getenv("S3_ACCESS_KEY"),
            "S3_SECRET_KEY": os.getenv("S3_SECRET_KEY"),
            "S3_BUCKET": os.getenv("S3_BUCKET"),
            "S3_REGION": os.getenv("S3_REGION", "us-east-1"),
            "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
            "VECTOR_STORE_ID": os.getenv("VECTOR_STORE_ID"),
        }
        
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        
        # Parse additional extensions (non-Google Workspace files)
        # Google Docs/Sheets/Slides are handled separately via GOOGLE_MIME_EXPORTS
        ext_str = os.getenv("ADDITIONAL_EXTENSIONS", ".pdf,.doc,.docx,.ppt,.pptx,.txt,.rtf,.epub")
        extensions = [ext.strip() for ext in ext_str.split(",")]
        
        return cls(
            google_service_account_file=required["GOOGLE_SERVICE_ACCOUNT_FILE"],
            google_drive_folder_id=required["GOOGLE_DRIVE_FOLDER_ID"],
            s3_endpoint=required["S3_ENDPOINT"],
            s3_access_key=required["S3_ACCESS_KEY"],
            s3_secret_key=required["S3_SECRET_KEY"],
            s3_bucket=required["S3_BUCKET"],
            s3_region=required["S3_REGION"],
            openai_api_key=required["OPENAI_API_KEY"],
            vector_store_id=required["VECTOR_STORE_ID"],
            max_files_per_run=int(os.getenv("MAX_FILES_PER_RUN", "10")),
            additional_extensions=extensions,
            processor_max_workers=int(os.getenv("PROCESSOR_MAX_WORKERS", "5")),
            indexer_max_workers=int(os.getenv("INDEXER_MAX_WORKERS", "3")),
            processing_engine=os.getenv("PROCESSING_ENGINE", "unstructured"),  # "unstructured" or "docling"
            postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
            postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
            postgres_db=os.getenv("POSTGRES_DB", "ai_knowledge_base"),
            postgres_user=os.getenv("POSTGRES_USER", "postgres"),
            postgres_password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        )
