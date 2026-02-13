"""
Configuration settings for the RAG Agent.

These settings are used by the various RAG tools.
Vertex AI initialization is performed in the package's __init__.py
"""

import os

from dotenv import load_dotenv

# Load environment variables (this is redundant if __init__.py is imported first,
# but included for safety when importing config directly)
load_dotenv()

# Vertex AI settings
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", )
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "asia-east1")
RAG_BACKEND = os.environ.get("RAG_BACKEND", "vertex").lower()
USE_CHROMA = RAG_BACKEND == "chroma"
CHROMA_DB_PATH = os.environ.get("CHROMA_DB_PATH", ".chroma")
AZURE_EMBEDDING_MODEL = os.environ.get("AZURE_EMBEDDING_MODEL")
RAG_MODE = "local"
USE_CHROMA = "chroma"
EVAL_BUCKET_NAME = "Eval"

# RAG settings
DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 100
DEFAULT_TOP_K = 3
DEFAULT_DISTANCE_THRESHOLD = 0.5
DEFAULT_EMBEDDING_MODEL = "publishers/google/models/text-embedding-002"
DEFAULT_EMBEDDING_REQUESTS_PER_MIN = 1000

# Google Cloud Project Settings
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "prusandbx-nprd-uat-hqzxfl")  # Replace with your project ID
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "asia-east1") # Default location for Vertex AI resources use GA


# GCS Storage Settings
GCS_DEFAULT_STORAGE_CLASS = "STANDARD"
GCS_DEFAULT_LOCATION = "ASIA"
GCS_LIST_BUCKETS_MAX_RESULTS = 50
GCS_LIST_BLOBS_MAX_RESULTS = 100

# RAG Corpus Settings
RAG_DEFAULT_EMBEDDING_MODEL = "publishers/google/models/text-embedding-005"
RAG_DEFAULT_TOP_K = 10
RAG_DEFAULT_SEARCH_TOP_K = 5
RAG_DEFAULT_VECTOR_DISTANCE_THRESHOLD = 0.5
RAG_DEFAULT_CHUNK_SIZE = 512
RAG_DEFAULT_CHUNK_OVERLAP = 100
RAG_DEFAULT_EMBEDDING_REQUESTS_PER_MIN = 1000

# Logging Settings
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
AGENT_OUTPUT_KEY = "last_response"
 