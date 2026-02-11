import os
import sys
import argparse
import pandas as pd
import vertexai
from vertexai.preview import rag
import logging
from tqdm import tqdm

# --- Setup Project Path ---
# This allows the script to find the 'rag' and 'config' modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

try:
    from rag.config import PROJECT_ID, LOCATION
except ImportError:
    print("Error: Could not import configuration. Make sure you are running this script from the project root or have the project in your PYTHONPATH.")
    sys.exit(1)

# --- Logger Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_corpus_id_by_display_name(display_name: str) -> str | None:
    """
    Finds a corpus ID by its display name.
    """
    logger.info(f"Searching for corpus with display name: '{display_name}'...")
    try:
        corpora = rag.list_corpora()
        for corpus in corpora:
            if corpus.display_name == display_name:
                corpus_id = corpus.name.split('/')[-1]
                logger.info(f"Found corpus ID: {corpus_id}")
                return corpus_id
        logger.error(f"No corpus found with display name '{display_name}'.")
        return None
    except Exception as e:
        logger.error(f"An error occurred while listing corpora: {e}")
        return None


def export_all_chunks(corpus_id: str, output_csv_path: str):
    """
    Exports all chunks and their metadata from a given corpus to a CSV file.

    This function works by sending a broad query to the RAG service and requesting
    the maximum number of results (up to 1000 per query). It paginates through
    the results to retrieve all chunks.

    Args:
        corpus_id: The ID of the RAG corpus.
        output_csv_path: The path to save the output CSV file.
    """
    try:
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        corpus_name = f"projects/{PROJECT_ID}/locations/{LOCATION}/ragCorpora/{corpus_id}"
        logger.info(f"Starting chunk export for corpus: {corpus_name}")

        all_chunks = []
        page_token = None
        total_chunks_retrieved = 0

        with tqdm(desc="Retrieving chunks", unit=" chunks") as pbar:
            while True:
                # The query text can be a generic term or even empty.
                # We set a high similarity_top_k and a lenient threshold to get as many results as possible.
                response = rag.retrieval_query(
                    rag_resources=[rag.RagResource(rag_corpus=corpus_name)], # type: ignore
                    text=" ",  # A broad query
                    similarity_top_k=100, # Page size, keep it well below the 1000 limit to be safe.
                    vector_distance_threshold=1.0, # Most lenient threshold
                )

                if hasattr(response, "contexts") and hasattr(response.contexts, "contexts"):
                    contexts = response.contexts.contexts
                    for ctx in contexts:
                        all_chunks.append({
                            #"chunk_id": ctx.chunk_name.split('/')[-1],
                            "chunk_text": ctx.text,
                            "document_uri": ctx.source_uri,
                            "document_name": os.path.basename(ctx.source_uri),
                            "distance": ctx.distance,
                        })
                    
                    retrieved_count = len(contexts)
                    total_chunks_retrieved += retrieved_count
                    pbar.update(retrieved_count)

                # Check for the next page
                if hasattr(response, "next_page_token") and response.next_page_token:
                    page_token = response.next_page_token
                else:
                    break # No more pages

        logger.info(f"Successfully retrieved a total of {total_chunks_retrieved} chunks.")

        # Create DataFrame and save to CSV
        df = pd.DataFrame(all_chunks)
        df.to_csv(output_csv_path, index=False, encoding='utf-8')
        logger.info(f"Export complete. Data saved to '{output_csv_path}'")

    except Exception as e:
        logger.error(f"Failed to export chunks: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export all chunks and their IDs from a Vertex AI RAG Corpus.")
    parser.add_argument("corpus_display_name", type=str, help="The display name of the corpus to export from.")
    parser.add_argument("-o", "--output", type=str, default="corpus_chunks_export.csv", help="Path for the output CSV file. Defaults to 'corpus_chunks_export.csv'.")
    args = parser.parse_args()

    corpus_id = get_corpus_id_by_display_name(args.corpus_display_name)

    if corpus_id:
        export_all_chunks(corpus_id, args.output)

"""

### How to Use the Script

1.  **Save the file**: Create a new directory named `scripts` inside your `document-user-agentic-rag` project folder and save the code above as `export_corpus_chunks.py`.

2.  **Open your terminal**: Navigate to the root of your project directory (`document-user-agentic-rag`).

3.  **Run the script**: Execute the script from your terminal, providing the display name of the corpus you want to export.

   **Example:**
   If you want to export chunks from a corpus named `"gc-phkl-policy"`, you would run:

   ```bash
   python scripts/export_corpus_chunks.py "gc-phkl-policy"
   ```

4.  **Specify an output file (Optional)**:
   To save the output to a different file name or location, use the `-o` or `--output` flag:

   ```bash
   python scripts/export_corpus_chunks.py "gc-phkl-policy" -o ./exports/policy_chunks.csv
   ```

5.  **Check the output**: A CSV file (e.g., `corpus_chunks_export.csv`) will be created in your current directory. It will contain the following columns:
   *   `chunk_id`
   *   `chunk_text`
   *   `document_uri`
   *   `document_name`
   *   `distance` (from the broad query)


"""