import asyncio
import logging

import vertexai
from google.genai import types

from rag.agent import create_runner, root_agent
from rag.config import LOCATION, PROJECT_ID, RAG_DEFAULT_EMBEDDING_MODEL

logger = logging.getLogger(__name__)


try:
    if PROJECT_ID and LOCATION:
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        logger.info(f"Initialized Vertex AI with project {PROJECT_ID}, location={LOCATION} with {RAG_DEFAULT_EMBEDDING_MODEL}")
    else:
        logger.warning("PROJECT_ID or LOCATION not set. Vertex AI initialization skipped.")
except Exception as e:
    logger.error(f"Failed to initialize Vertex AI: {e}")


async def _run_once_async(
    user_input: str,
    app_name: str = "pru_rag_conversation",
    user_id: str = "local-user",
    session_id: str | None = None,
    agent_engine_id: str | None = None,
):
    runner = create_runner(app_name=app_name, agent_engine_id=agent_engine_id)

    if session_id is None:
        session = await runner.session_service.create_session(
            app_name=runner.app_name,
            user_id=user_id,
        )
        session_id = session.id
    else:
        session = await runner.session_service.get_session(
            app_name=runner.app_name,
            session_id=session_id,
            user_id=user_id,
        )

    content = types.UserContent(user_input)
    final_text = ""

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=content,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            part = event.content.parts[0]
            if getattr(part, "text", None):
                final_text = part.text

    return final_text, session_id


def run_once(
    user_input: str,
    app_name: str = "pru_rag_conversation",
    user_id: str = "local-user",
    session_id: str | None = None,
    agent_engine_id: str | None = None,
):
    return asyncio.run(
        _run_once_async(
            user_input=user_input,
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            agent_engine_id=agent_engine_id,
        )
    )
