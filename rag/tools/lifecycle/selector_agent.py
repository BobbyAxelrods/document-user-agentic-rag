import os
from google.adk.agents import Agent

model = os.getenv("MODEL_NAME", "gemini-1.5-flash")

CORPUS_SELECTOR_INSTRUCTION = """
Based on your understanding towards the user's query, you must decide which corpus to use.

Your output MUST be one of the following two options, and nothing else:
- "gc-phkl-policy"
- "gc-phkl-vas"

Follow these rules strictly:
1. If the query is related to a policy or a product, especially if it contains "pru" or "prudential", you must output "gc-phkl-policy".
2. If the query is more general, or about a specific topic or a rider product that is not a base policy, you must output "gc-phkl-vas".

Analyze the user's query and return only the name of the corpus to use.
"""

corpus_selector_agent = Agent(
    name="corpus_selector",
    model=model,
    instruction=CORPUS_SELECTOR_INSTRUCTION,
    description="Selects the appropriate RAG corpus ('gc-phkl-policy' or 'gc-phkl-vas') based on the user's query.",
    # This agent doesn't need tools, it just makes a decision based on the prompt.
    tools=[],
    output_key="selected_corpus"
)