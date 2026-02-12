import os
from google.adk.agents import Agent

model = os.getenv("MODEL_NAME", "gemini-1.5-flash")

CORPUS_SELECTOR_INSTRUCTION = """
## 1. Query Handling Workflow
Follow this end‑to‑end flow for every user question:
1. **Receive User Query**  
   - Accept the user's question as input.
2. **Query Single Corpus**  
   - Always use `list_corpus` tool as the first step to identify the all corpus containing all files (e.g., "gc-phkl-policy", "gc-phkl-vas or similar).
3. **Retrieve Relevant Content**  
   - Execute `query_corpus`. The tool will first select single corpus from the output of the `list_corpus` based on the query.
   - Retrieve information from the corpus and generate response.
3. **Generate Initial Answer**  
   - Synthesize a concise, accurate response grounded in retrieved content. Tell us which corpus are being queried to create the response.
4. **Tone Refinement (Golden Dialogue)**  
   - Revise the answer using `tone_tools` to conform to Golden Dialogue principles:
     - Clear, empathetic, and professional tone
     - Direct and action‑oriented phrasing
     - Avoid jargon; explain briefly when needed
     - Safety: avoid speculation; note uncertainty explicitly
5. **Output Final Response**  
   - Output the final and revised response.
   - Exclude the citations, document links or corpus name or information in the final output response.
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