import os
from google.adk.agents import Agent

model = os.getenv("MODEL_NAME", "gemini-1.5-flash")

CORPUS_SELECTOR_INSTRUCTION = """
Follow this end‑to‑end flow for every user question:
1. **Receive User Query**  
   - Accept the user's question as input.
2. **Query Single Corpus**  
   - Use `list_corpus` to identify the all corpus containing all files (e.g., "gc-phkl-policy", "gc-phkl-vas or similar).
   - Based on your understanding towards the user's query, select the most relevant corpus based on the following criteria:
    1. If the query is related to Prudential insurance policy or product, with prefix "PRU" or "prudential", refer to the corpus named "gc-phkl-policy" and "Policy Documents". 
    2. Else if the query is related to more general query towards a specific topic or rider product, refer to the corpus named "gc-phkl-vas". 
    3. If you cannot determine which corpus to use, use the "gc-phkl-policy" corpus by default. 
    4. Do not ever ask the user to provide the corpus name or id. Think and come up with a corpus name and their respective corpus id.
   - Execute `query_corpus` against the selected single corpus.
3. **Output Final Response** 
"""

corpus_selector_agent = Agent(
    name="corpus_selector",
    model=model,
    instruction=CORPUS_SELECTOR_INSTRUCTION,
    description="Selects the appropriate RAG corpus ('gc-phkl-policy' or 'gc-phkl-vas' or 'Policy Documents) based on the user's query.",
    # This agent doesn't need tools, it just makes a decision based on the prompt.
    tools=[],
    output_key="selected_corpus"
)