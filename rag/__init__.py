# Main package initialization
from rag.agent import root_agent
import logging
import vertexai
from rag.config import PROJECT_ID, LOCATION, RAG_DEFAULT_EMBEDDING_MODEL
logger = logging.getLogger(__name__)


try:
    if PROJECT_ID and LOCATION:
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        logger.info(f"Initialized Vertex AI with project {PROJECT_ID}, location={LOCATION} with {RAG_DEFAULT_EMBEDDING_MODEL}")
    else:
        logger.warning("PROJECT_ID or LOCATION not set. Vertex AI initialization skipped.")
except Exception as e:
    logger.error(f"Failed to initialize Vertex AI: {e}")
