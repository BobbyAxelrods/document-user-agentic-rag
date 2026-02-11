import os 
import hashlib
import json
import io
import time
import pandas as pd 
import datetime
import pg8000
import re
import vertexai
from google.cloud.sql.connector import Connector, IPTypes
import logging
from google.cloud import storage
from google.adk.tools import FunctionTool, ToolContext
import litellm
from typing import Any, Optional, List, Dict
import sys
from google.cloud.sql.connector import Connector, IPTypes
from thefuzz import fuzz
from dotenv import load_dotenv
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
import math

# Import corpus tools
try:
    from tools.corpus.corpus_tools import (
        get_corpus_id_by_display_name,
        query_corpus,
        import_files,
        delete_file_from_corpus,
        create_corpus,
        delete_corpus,
        list_corpora,
        list_files
    )
    from tools.storage.storage_tools import create_gcs_bucket, list_blobs
    from tools.lifecycle.selector_agent import CORPUS_SELECTOR_INSTRUCTION
    from config import (
        PROJECT_ID, 
        LOCATION, 
        RAG_DEFAULT_TOP_K,
        EVAL_BUCKET_NAME,
    )
except ImportError:
    try:
        from rag.tools.corpus.corpus_tools import (
            get_corpus_id_by_display_name,
            query_corpus,
            import_files,
            delete_file_from_corpus,
            create_corpus,
            delete_corpus,
            list_corpora,
            list_files
        )
        from rag.tools.storage.storage_tools import create_gcs_bucket, list_blobs
        from rag.tools.lifecycle.selector_agent import CORPUS_SELECTOR_INSTRUCTION
        from rag.config import (
            PROJECT_ID, 
            LOCATION, 
            RAG_DEFAULT_TOP_K,
            EVAL_BUCKET_NAME,
        )
    except ImportError:
        from ...tools.corpus.corpus_tools import (
            get_corpus_id_by_display_name,
            query_corpus,
            import_files,
            delete_file_from_corpus,
            create_corpus,
            delete_corpus,
            list_corpora,
            list_files
        )
        from ...tools.storage.storage_tools import create_gcs_bucket, list_blobs
        from ...tools.lifecycle.selector_agent import CORPUS_SELECTOR_INSTRUCTION
        from ...config import (
            PROJECT_ID, 
            LOCATION, 
            RAG_DEFAULT_TOP_K,
            EVAL_BUCKET_NAME,
        )

### storage client initi
# Initialize Storage Client
try:
    storage_client = storage.Client(project=PROJECT_ID)
except Exception as e:
    logger.error(f"Failed to initialize storage client: {e}")
    storage_client = None

# Initialize Vertex AI
try:
    if PROJECT_ID and LOCATION:
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        logging.info(f"Initialized Vertex AI with project {PROJECT_ID}, location={LOCATION}")
    else:
        logging.warning("PROJECT_ID or LOCATION not set. Vertex AI initialization skipped.")
except Exception as e:
    logging.error(f"Failed to initialize Vertex AI: {e}")


# Logger setup
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def _normalize_filename(uri: str) -> str:
    """
    Extracts the base filename (lowercase, no extension) from a URI or file path.
    Example: "gs://bucket/folder/File-Name.pdf" -> "file-name"
    Handles removing parenthesis content and normalizing separators.
    """
    if not uri or pd.isna(uri):
        return ""
    
    # 1. Get basename
    base = os.path.basename(str(uri))
    
    # 2. Remove extension
    name = os.path.splitext(base)[0]
    
    # 3. Remove content in parentheses (e.g. "Treatment Sure (webpage)" -> "Treatment Sure")
    name = re.sub(r'\([^)]*\)', '', name)
    
    # 4. Replace special chars ([-_]) with space
    name = re.sub(r'[-_]', ' ', name)
    
    # 5. Normalize whitespace (strip and collapse multiple spaces)
    name = " ".join(name.split())
    
    return name.lower()

def _calculate_retrieval_metrics(retrieved_chunk: List[str], ground_truth_chunk: List[str], retrieved_uris: List[str], ground_truth_docs: List[str], retrieved_corpus: str, ground_truth_corpus: str, k_doc: int = 20, k_chunk: int = 20, k_corpus: int = 20) -> Dict[str, float]:
    """
    Calculates Recall, Precision, and NDCG for retrieval of chunk and docs.
    """
    # Normalize inputs
    retrieved_norm_raw_doc = [_normalize_filename(u) for u in retrieved_uris]
    retrieved_norm_raw_chunk = [_normalize_filename(u) for u in retrieved_chunk]
    retrieved_norm_raw_corpus = [_normalize_filename(u) for u in retrieved_corpus]

    gt_norm_doc = set([_normalize_filename(g) for g in ground_truth_docs if _normalize_filename(g)])
    gt_norm_chunk = set([_normalize_filename(g) for g in ground_truth_chunk if _normalize_filename(g)])
    gt_norm_corpus = set([_normalize_filename(g) for g in ground_truth_corpus if _normalize_filename(g)])
    
    if not gt_norm_doc and not gt_norm_chunk and not gt_norm_corpus:
        return {"recall_doc": 0.0, "precision_doc": 0.0, "ndcg_doc": 0.0,
                "recall_chunk": 0.0, "precision_chunk": 0.0, "ndcg_chunk": 0.0,
                "recall_corpus": 0.0, "precision_corpus": 0.0, "ndcg_corpus": 0.0
                }

    # Deduplicate retrieved items based on Ground Truth matching (Strict Document Level)
    # 1. Map each retrieved item to its matched GT document (if any)
    # 2. Deduplicate the resulting list preserving order
    retrieved_unique = []
    seen_docs = set() # Stores the normalized doc string (either GT name or original doc name)

    for doc in retrieved_norm_raw_doc:
        # Check if this doc matches any Ground Truth
        matched_gt_doc = None
        for gt in gt_norm_doc:
            # Match if strings are equal, or one is substring of another
            if fuzz.partial_ratio(doc, gt) > 90:
                matched_gt_doc = gt # Use the GT doc for canonical representation
                break
        
        # Use the matched GT name if found, otherwise use the original doc name
        item_to_add = matched_gt_doc if matched_gt_doc else doc
        
        if item_to_add not in seen_docs:
            retrieved_unique.append(item_to_add)
            seen_docs.add(item_to_add)

    # Slice to top K (Document Level)
    retrieved_k_doc = retrieved_unique[:k_doc]
    print(f"retrieved_k_doc: {retrieved_k_doc}")
    # Calculate Matches (Strict Document Level)
    matches_count = 0
    dcg = 0.0
    
    for i, doc in enumerate(retrieved_k_doc):
        # Check strict existence in GT set (since we already mapped them)
        if doc in gt_norm_doc:
            matches_count += 1
            # DCG: Binary relevance = 1
            dcg += 1.0 / math.log2(i + 2)

    # 1. Recall (Document-Level)
    # Unique Matches / Total Unique GT
    recall_doc = matches_count / len(gt_norm_doc)
    
    # 2. Precision (Document-Level)
    # Unique Matches / Total Unique Retrieved (Dynamic K)
    # This ensures 1/1 = 1.0 (100%)
    precision_doc = matches_count / len(retrieved_k_doc) if retrieved_k_doc else 0.0
    
    # 3. NDCG (Document-Level)
    # IDCG based on Ideal Ranking of the retrieved set size
    # This ensures perfect ranking of available items = 1.0
    idcg = 0.0
    num_ideal_matches = min(len(gt_norm_doc), len(retrieved_k_doc))
    for i in range(num_ideal_matches):
        idcg += 1.0 / math.log2(i + 2)
        
    ndcg_doc = dcg / idcg if idcg > 0 else 0.0

    # Deduplicate retrieved items based on Ground Truth matching (Strict Chunk Level)
    # 1. Map each retrieved item to its matched GT Chunk (if any)
    # 2. Deduplicate the resulting list preserving order
    retrieved_unique = []
    seen_chunks = set() # Stores the normalized chunk string

    for chunk in retrieved_norm_raw_chunk:
        # Check if this chunk matches any Ground Truth
        matched_gt_chunk = None
        for gt in gt_norm_chunk:
            # Match if strings are equal, or one is substring of another
            if fuzz.partial_ratio(chunk, gt) > 90:
                matched_gt_chunk = gt # Use the GT chunk for canonical representation
                break
        
        # Use the matched GT name if found, otherwise use the original chunk
        item_to_add = matched_gt_chunk if matched_gt_chunk else chunk
        
        if item_to_add not in seen_chunks:
            retrieved_unique.append(item_to_add)
            seen_chunks.add(item_to_add)

    # Slice to top K (Chunk Level)
    retrieved_k_chunk = retrieved_unique[:k_chunk]
    print(f"retrieved_k_chunk: {retrieved_k_chunk}")
    
    # Calculate Matches (Strict Chunk Level)
    matches_count = 0
    dcg = 0.0
    
    for i, doc in enumerate(retrieved_k_chunk):
        # Check strict existence in GT set (since we already mapped them)
        if doc in gt_norm_chunk:
            matches_count += 1
            # DCG: Binary relevance = 1
            dcg += 1.0 / math.log2(i + 2)

    # 1. Recall (Chunk-Level)
    # Unique Matches / Total Unique GT
    recall_chunk = matches_count / len(gt_norm_chunk)
    
    # 2. Precision (Chunk-Level)
    # Unique Matches / Total Unique Retrieved (Dynamic K)
    # This ensures 1/1 = 1.0 (100%)
    precision_chunk = matches_count / len(retrieved_k_chunk) if retrieved_k_chunk else 0.0
    
    # 3. NDCG (Chunk-Level)
    # IDCG based on Ideal Ranking of the retrieved set size
    # This ensures perfect ranking of available items = 1.0
    idcg = 0.0
    num_ideal_matches = min(len(gt_norm_chunk), len(retrieved_k_chunk))
    for i in range(num_ideal_matches):
        idcg += 1.0 / math.log2(i + 2)
        
    ndcg_chunk = dcg / idcg if idcg > 0 else 0.0

    # Deduplicate retrieved items based on Ground Truth matching (Strict Corpus Level)
    # 1. Map each retrieved item to its matched GT corpus (if any)
    # 2. Deduplicate the resulting list preserving order
    retrieved_unique = []
    seen_corpus = set() # Stores the normalized corpus string

    for corpus in retrieved_norm_raw_corpus:
        # Check if this corpus matches any Ground Truth
        matched_gt_corpus = None
        for gt in gt_norm_corpus:
            # Match if strings are equal, or one is substring of another
            if fuzz.partial_ratio(corpus, gt) > 90:
                matched_gt_corpus = gt # Use the GT chunk for canonical representation
                break
        
        # Use the matched GT name if found, otherwise use the original corpus
        item_to_add = matched_gt_corpus if matched_gt_corpus else corpus
        
        if item_to_add not in seen_corpus:
            retrieved_unique.append(item_to_add)
            seen_corpus.add(item_to_add)

    # Slice to top K (Chunk Level)
    retrieved_k_corpus = retrieved_unique[:k_corpus]
    print(f"retrieved_k_corpus: {retrieved_k_corpus}")
    
    # Calculate Matches (Strict Chunk Level)
    matches_count = 0
    dcg = 0.0
    
    for i, doc in enumerate(retrieved_k_corpus):
        # Check strict existence in GT set (since we already mapped them)
        if doc in gt_norm_corpus:
            matches_count += 1
            # DCG: Binary relevance = 1
            dcg += 1.0 / math.log2(i + 2)

    # 1. Recall (Chunk-Level)
    # Unique Matches / Total Unique GT
    recall_corpus = matches_count / len(gt_norm_corpus)
    
    # 2. Precision (corpus-Level)
    # Unique Matches / Total Unique Retrieved (Dynamic K)
    # This ensures 1/1 = 1.0 (100%)
    precision_corpus = matches_count / len(retrieved_k_corpus) if retrieved_k_corpus else 0.0
    
    # 3. NDCG (corpus-Level)
    # IDCG based on Ideal Ranking of the retrieved set size
    # This ensures perfect ranking of available items = 1.0
    idcg = 0.0
    num_ideal_matches = min(len(gt_norm_corpus), len(retrieved_k_corpus))
    for i in range(num_ideal_matches):
        idcg += 1.0 / math.log2(i + 2)
        
    #ndcg_corpus = dcg / idcg if idcg > 0 else 0.0
    
    return {
        "recall_doc": round(recall_doc, 4),
        "precision_doc": round(precision_doc, 4),
        "ndcg_doc": round(ndcg_doc, 4),
        "recall_chunk": round(recall_chunk, 4),
        "precision_chunk": round(precision_chunk, 4),
        "ndcg_chunk": round(ndcg_chunk, 4),
        "recall_corpus": round(recall_corpus, 4),
        "precision_corpus": round(precision_corpus, 4),
        #"ndcg_corpus": round(ndcg_corpus, 4)
    }


def _evaluate_with_llm(query: str, response: str, ground_truth: str) -> Dict[str, Any]:
    """
    Evaluates RAG response against ground truth using LiteLLM (matching Agent's config).
    """
    try:
        model_name = os.getenv("MODEL_NAME", "gemini-2.5-pro")
        
        prompt = f"""
        You are an expert evaluator for RAG systems.
        
        Query: {query}
        Generated Response (Retrieved Context): {response}
        Ground Truth: {ground_truth}
        
        Task:
        1. Compare the Generated Response with the Ground Truth.
        2. Assign a score between 0.0 and 1.0 (1.0 being perfect match in meaning).
        3. Provide a brief reason.
        
        Output JSON format:
        {{
            "score": float,
            "reason": "string"
        }}
        """
        
        completion = litellm.completion(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a helpful assistant designed to output JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={ "type": "json_object" }
        )
        
        content = completion.choices[0].message.content
        eval_data = json.loads(content)
        #eval_data['bleu_score'] = bleu_score
        return eval_data

    except Exception as e:
        return {"score": 0.0, "reason": f"Evaluation failed: {str(e)}"}

def _generate_answer(query: str, context: str) -> str:
    
    """
    Generates an answer based on the query and retrieved context using the LLM.
    """
    try:
        model_name = os.getenv("MODEL_NAME", "gemini-2.5-pro")

        prompt = f"""
        You are a helpful assistant. Answer the user's query based ONLY on the provided context.
        If the answer is not in the context, say "I cannot answer this based on the provided information."
        
        Context:
        {context}
        
        Query: 
        {query}
        
        Answer:
        """
        
        completion = litellm.completion(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        
        return completion.choices[0].message.content.strip()
    except Exception as e:
        return f"Generation failed: {str(e)}"

def _refine_tone_with_golden_dialogue(answer: str) -> str:
    """
    Refines the answer's tone using an LLM to conform to Golden Dialogue principles.
    """
    try:
        model_name = os.getenv("MODEL_NAME", "gemini-1.5-pro")

        prompt = f"""
        You are an expert in communication, tasked with refining an answer to align with "Golden Dialogue" principles.

        Golden Dialogue Principles:
        - **Clarity & Empathy**: Be clear, empathetic, and professional.
        - **Action-Oriented**: Use direct and action-oriented phrasing.
        - **Simplicity**: Avoid jargon. If jargon is necessary, explain it briefly.
        - **Safety**: Avoid speculation. If there is uncertainty, state it explicitly.

        Original Answer:
        {answer}

        Task:
        Revise the original answer to strictly follow the Golden Dialogue principles.
        Do not add any new information.
        If the original answer indicates it cannot answer, keep that meaning.

        Revised Answer:
        """

        completion = litellm.completion(
            model=model_name,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Tone refinement failed: {e}")
        return answer # Return original answer if refinement fails

def _select_corpus_with_llm(query: str) -> str:
    """
    Uses an LLM to select the appropriate corpus based on the query.
    This replicates the logic of the corpus_selector_agent.
    """
    try:
        model_name = os.getenv("MODEL_NAME", "gemini-1.5-flash")
        prompt = f"""
                {CORPUS_SELECTOR_INSTRUCTION}

                User Query: "{query}"
                """
        completion = litellm.completion(
            model=model_name,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        # The agent is instructed to return *only* the corpus name.
        selected_corpus = completion.choices[0].message.content.strip()
        
        # Basic validation to ensure it's one of the expected outputs
        if selected_corpus in ["gc-phkl-policy", "gc-phkl-vas"]:
            return selected_corpus
        return "gc-phkl-vas" # Default fallback
    except Exception as e:
        logger.warning(f"Corpus selection with LLM failed: {e}. Defaulting to 'gc-phkl-vas'.")
        return "gc-phkl-vas"
# =================MAIN PROCESS =====================
# =================MAIN PROCESS =====================
def automated_evaluation_testcase(
    tool_context : ToolContext
) -> Dict[str,Any]:

    """
    Plan:

    1. Read the Excel file using pandas .
    2. Iterate through the rows.
    3. For each row, execute a RAG query using query_corpus .
    4.  Compare the result with the ground truth using an LLM as a judge ().
    5. Update the pandas DataFrame with the results (RAG response, Score, Pass/Fail status).
    6. Return the final DataFrame (as a dict/list of records) and summary statistics.

    """

    # Read Excel from local
    excel_path = "./evaluation_files/EMO, POLICY & VAS QA_updated.xlsx"
    df = pd.read_excel(excel_path, sheet_name="Sheet2")


    
    # Identify columns (flexible) by checking lowercase stripped versions but keeping original headers
    # Create a mapping for easy lookup
    col_map = {str(c).lower().strip(): c for c in df.columns}
    
    # Find actual column names in the dataframe
    query_col_name = next((c for c in col_map.keys() if c in ['query', 'question', 'input', 'user query']), list(col_map.keys())[0])
    truth_col_name = next((c for c in col_map.keys() if c in ['ground_truth', 'ground truth', 'groundtruth', 'expected', 'truth', 'answer', 'correct answer']), None)
    doc_truth_col_name = next((c for c in col_map.keys() if c in ['ground truth documents uri', 'document uri', 'source documents', 'ground truth documents']), None)
    chunk_truth_col_name = next((c for c in col_map.keys() if c in ['ground truth chunk', 'chunk match']), None)
    corpus_truth_col_name = next((c for c in col_map.keys() if c in ['ground truth corpus', 'corpus match', 'corpus name', 'corpus uri', 'corpura']), None)

    query_col = col_map[query_col_name]
    truth_col = col_map[truth_col_name] if truth_col_name else None
    doc_truth_col = col_map[doc_truth_col_name] if doc_truth_col_name else None
    chunk_truth_col = col_map[chunk_truth_col_name] if chunk_truth_col_name else None
    corpus_truth_col = col_map[corpus_truth_col_name] if corpus_truth_col_name else None

    # Loop and Validate
    total_bleu_score = 0
    total_recall_doc = 0.0
    total_precision_doc = 0.0
    total_ndcg_doc = 0.0
    total_recall_chunk = 0.0
    total_precision_chunk = 0.0
    total_ndcg_chunk = 0.0
    total_recall_corpus = 0.0
    total_precision_corpus = 0.0
    #total_ndcg_corpus = 0.0

    pass_count = 0
    evaluated_rows = []

    # Setup for continuous save
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    date_folder = datetime.datetime.now().strftime("%Y-%m-%d")
    base_name = os.path.splitext(os.path.basename(excel_path))[0]
    
    # Define temporary and final paths
    temp_blob_path = f"evaluation_files/temp_processing/{base_name}_{timestamp}_working.xlsx"
    final_blob_path = f"evaluation_files/eval_results/{date_folder}/{base_name}_results_{timestamp}.xlsx"

    # Helper to save current progress to GCS
    def save_progress_to_gcs(current_rows, blob_path, is_temp=True):
        if not storage_client: return
        try:
            temp_df = pd.DataFrame(current_rows)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                temp_df.to_excel(writer, index=False)
            output_bytes = output.getvalue()
            
            bucket = storage_client.bucket(EVAL_BUCKET_NAME)
            blob = bucket.blob(blob_path)
            blob.upload_from_string(
                data=output_bytes,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            if not is_temp:
                logger.info(f"Saved results to gs://{EVAL_BUCKET_NAME}/{blob_path}")
        except Exception as e:
            logger.warning(f"Failed to save progress to {blob_path}: {e}")

    # 1. Upload initial file to temp location
    try:
        if storage_client:
            bucket = storage_client.bucket(EVAL_BUCKET_NAME)
            if not bucket.exists():
                create_gcs_bucket(tool_context=tool_context, bucket_name=EVAL_BUCKET_NAME, location=LOCATION)
            
            # Read bytes from local file
            with open(excel_path, "rb") as f:
                bucket.blob(temp_blob_path).upload_from_file(f)
            logger.info(f"Uploaded working copy to gs://{EVAL_BUCKET_NAME}/{temp_blob_path}")
    except Exception as e:
        logger.warning(f"Failed to upload initial working copy: {e}")
    
    try:
        df_eval = pd.DataFrame()
        for index, row in df.iterrows():
            # Add delay to avoid hitting rate limits (LLM/Vertex AI quotas)
            time.sleep(2)
            
            query_text = str(row[query_col])
            # Use the identified truth column, but keep strict N/A handling for evaluation
            ground_truth = str(row[truth_col]) if truth_col and truth_col in df.columns else "N/A"
            if ground_truth.lower() == 'nan': ground_truth = "N/A"
            
            # --- Start of New Agent-like Logic ---

            # 2. Select Corpus based on query
            # Use the selector agent to decide the corpus
            target_corpus_display_name = _select_corpus_with_llm(query_text)

            corpus_id = get_corpus_id_by_display_name(target_corpus_display_name)
            if not corpus_id:
                # Fallback to the original candidate_corpus if the specific one isn't found
                logger.warning(f"Could not find corpus '{target_corpus_display_name}'. Falling back to '{candidate_corpus}'.")
                corpus_id = get_corpus_id_by_display_name(candidate_corpus)
                if not corpus_id:
                     # If fallback also fails, we must skip this row.
                    logger.error(f"Fallback corpus '{candidate_corpus}' also not found. Skipping row {index + 1}.")
                    response_text = f"Error: Corpus '{target_corpus_display_name}' or fallback '{candidate_corpus}' not found."
                    citations, chunks = [], []
                    # Continue to evaluation to mark it as a failure
                
            # 3. Query Corpus and Generate Initial Answer
            response_text = "No response"
            citations, chunks, document_names, retrieved_uris = [], [], [], []

            if corpus_id:
                rag_result = query_corpus(corpus_id=corpus_id, query=query_text)
                
                if rag_result.get("status") == "success" and "results" in rag_result and rag_result["results"]:
                    # Get top 5 chunks for context
                    top_results = rag_result["results"][:1]
                    
                    # Prepare context from chunks
                    context_text = "\n\n".join([r.get("text", "") for r in top_results])
                    
                    # Generate Initial Answer using LLM
                    initial_answer = _generate_answer(query_text, context_text)

                    # Collect URIs for retrieval evaluation (Use ALL retrieved results, not just top 5)
                    retrieved_uris = [r.get("source_uri", "") for r in rag_result["results"]]

                    # Refine Tone with Golden Dialogue
                    response_text = _refine_tone_with_golden_dialogue(initial_answer)
                    
                    # Extract chunk details and citations
                    chunks = [r.get("text", "") for r in top_results]
                    document_names = [os.path.basename(r.get("source_uri", "Unknown")) for r in top_results]
                    citations = list(set([r.get("source_uri", "Unknown") for r in top_results if r.get("source_uri")]))
                else:
                    response_text = "Could not retrieve any information from the corpus to answer the query."
                    
                # Calculate BLEU score
                reference = [ground_truth.split()]
                candidate = response_text.split()
                # Using smoothing function to avoid 0 scores for sentences with no overlapping n-grams
                smoothie = SmoothingFunction().method4
                bleu_score = sentence_bleu(reference, candidate, smoothing_function=smoothie)

            # --- Retrieval Evaluation (New) ---
            retrieval_metrics = {"recall_doc": 0.0, "precision_doc": 0.0, "ndcg_doc": 0.0, 
                                "recall_chunk": 0.0, "precision_chunk": 0.0, "ndcg_chunk": 0.0,
                                "recall_corpus": 0.0, "precision_corpus": 0.0, "ndcg_c": 0.0
                                }
            if doc_truth_col and doc_truth_col in df.columns and chunk_truth_col and chunk_truth_col in df.columns and corpus_truth_col and corpus_truth_col in df.columns:
                raw_gt_docs = str(row[doc_truth_col])
                raw_gt_chunks = str(row[chunk_truth_col])
                raw_gt_corpus = str(row[corpus_truth_col])
                if raw_gt_docs.lower() != 'nan' and raw_gt_chunks.lower() != 'nan' and raw_gt_corpus.lower() != 'nan':
                    # Split by comma if multiple docs
                    gt_docs_list = [d.strip() for d in raw_gt_docs.split(',')]
                    print(f"gt_doc: {gt_docs_list}")
                    gt_chunks_list = [raw_gt_chunks]
                    print(f"gt_chunk: {gt_chunks_list}")
                    gt_corpus_list = [raw_gt_corpus]
                    print(f"gt_corpus: {gt_corpus_list}")
                    retrieval_metrics = _calculate_retrieval_metrics(chunks, gt_chunks_list, retrieved_uris, gt_docs_list, target_corpus_display_name, gt_corpus_list, k_doc=1, k_chunk=RAG_DEFAULT_TOP_K, k_corpus=1)
                    
            # --- End of New Agent-like Logic ---
            
            # Evaluate
            eval_result = _evaluate_with_llm(query_text, response_text, ground_truth)
            #score = eval_result.get("score", 0.0)
            

            is_pass = bleu_score >= 0.7
            if is_pass: pass_count += 1
            total_bleu_score += bleu_score
            
            # Construct Output Row:
            # 1. Start with original row data to preserve structure and values
            out_row = row.to_dict()
            
            # 2. Append new results columns
            out_row['rag_response'] = response_text[:1000] + "..." if len(response_text) > 1000 else response_text
            
            # Add Retrieval Metrics
            out_row['retrieval_recall_doc'] = retrieval_metrics['recall_doc']
            out_row['retrieval_precision_doc'] = retrieval_metrics['precision_doc']
            out_row['retrieval_ndcg_doc'] = retrieval_metrics['ndcg_doc']

            out_row['retrieval_recall_chunk'] = retrieval_metrics['recall_chunk']
            out_row['retrieval_precision_chunk'] = retrieval_metrics['precision_chunk']
            out_row['retrieval_ndcg_chunk'] = retrieval_metrics['ndcg_chunk']

            out_row['retrieval_recall_corpus'] = retrieval_metrics['recall_corpus']
            out_row['retrieval_precision_corpus'] = retrieval_metrics['precision_corpus']
            #out_row['retrieval_ndcg_corpus'] = retrieval_metrics['ndcg_corpus']

            # Aggregate metrics
            total_recall_doc += retrieval_metrics['recall_doc']
            total_precision_doc += retrieval_metrics['precision_doc']
            total_ndcg_doc += retrieval_metrics['ndcg_doc']

            total_recall_chunk += retrieval_metrics['recall_chunk']
            total_precision_chunk += retrieval_metrics['precision_chunk']
            total_ndcg_chunk += retrieval_metrics['ndcg_chunk']

            total_recall_corpus += retrieval_metrics['recall_corpus']
            total_precision_corpus += retrieval_metrics['precision_corpus']
            #total_ndcg_corpus += retrieval_metrics['ndcg_corpus']

            retrieve_k_chunk = 2

            # Add top 2 chunks and their details
            for i in range(retrieve_k_chunk):
                out_row[f'retrieved_chunk_{i+1}'] = chunks[i] if i < len(chunks) else ""
                out_row[f'retrieved_document_name_{i+1}'] = document_names[i] if i < len(document_names) else ""

            out_row['retrieved_citations'] = ", ".join(citations)
            out_row['bleu_score'] = bleu_score
            out_row['status'] = "PASS" if is_pass else "FAIL"
            out_row['reason'] = eval_result.get("reason", "")
            out_row['row_id'] = index + 1
            out_row['retrieved_corpus'] = target_corpus_display_name
            
            # Sanitize for JSON/LiteLLM compatibility (handle NaN, Timestamp, etc.)
            for k, v in out_row.items():
                if pd.isna(v):  # Handles NaN, None, NaT
                    out_row[k] = None
                elif isinstance(v, (pd.Timestamp, datetime.datetime, datetime.date)):
                    out_row[k] = str(v)
            
            evaluated_rows.append(out_row)
            df_eval = pd.DataFrame(evaluated_rows)
            df_eval = df_eval[['Question', 'Ground Truth', 'rag_response', 'corpus match', 'retrieved_corpus',
                                'document uri', 'retrieved_citations', 'chunk match'] + [f'retrieved_chunk_{i+1}' for i in range(0, retrieve_k_chunk)] 
                                + ['bleu_score', 'retrieval_recall_doc', 'retrieval_recall_chunk', 'retrieval_recall_corpus',
                               'retrieval_precision_doc', 'retrieval_precision_chunk', 'retrieval_precision_corpus',
                               'retrieval_ndcg_doc', 'retrieval_ndcg_chunk', 'status', 'reason']]
            print(df_eval.columns)
            
            # Checkpoint every 5 rows
            if (index + 1) % 5 == 0:
                save_progress_to_gcs(evaluated_rows, temp_blob_path, is_temp=True)

    except Exception as e:
        logger.error(f"Regression test interrupted: {e}")
        # Try to save whatever we have so far
        save_progress_to_gcs(evaluated_rows, temp_blob_path, is_temp=True)
        return {
            "status": "error", 
            "message": f"Regression test failed/interrupted: {str(e)}", 
            "partial_results_uri": f"gs://{EVAL_BUCKET_NAME}/{temp_blob_path}"
        }

    avg_bleu_score = total_bleu_score / len(df) if len(df) > 0 else 0
    avg_recall_doc = total_recall_doc / len(df) if len(df) > 0 else 0
    avg_precision_doc = total_precision_doc / len(df) if len(df) > 0 else 0
    avg_ndcg_doc = total_ndcg_doc / len(df) if len(df) > 0 else 0

    avg_recall_chunk = total_recall_chunk / len(df) if len(df) > 0 else 0
    avg_precision_chunk = total_precision_chunk / len(df) if len(df) > 0 else 0
    avg_ndcg_chunk = total_ndcg_chunk / len(df) if len(df) > 0 else 0

    failures = [r["row_id"] for r in evaluated_rows if r["status"] == "FAIL"]
    
    # Save results directly to GCS
    results_gcs_uri = ""
    try:
        # Save final to output folder
        save_progress_to_gcs(evaluated_rows, final_blob_path, is_temp=False)
        results_gcs_uri = f"gs://{EVAL_BUCKET_NAME}/{final_blob_path}"

        # Clean up temp file
        if storage_client:
            try:
                bucket = storage_client.bucket(EVAL_BUCKET_NAME)
                blob = bucket.blob(temp_blob_path)
                if blob.exists():
                    blob.delete()
                    logger.info(f"Deleted temporary working file: {temp_blob_path}")
            except Exception as e:
                logger.warning(f"Failed to delete temp file {temp_blob_path}: {e}")

    except Exception as e:
        logger.error(f"Failed to save/upload regression results: {e}")
        results_gcs_uri = f"Error: {str(e)}"

    df_eval.to_excel("/home/sinkitlo/guided_care/document-user-agentic-rag/evaluation_files/eval_results.xlsx", index=False)
    return {
        "status": "success",
        "project_id": PROJECT_ID,
        "results_file_uri": results_gcs_uri,
        "summary": {
            "total_queries": len(df),
            "passed": pass_count,
            "failed": len(failures),
            "average_bleu_score": round(avg_bleu_score, 2),
            "average_recall_doc": round(avg_recall_doc, 4),
            "average_precision_doc": round(avg_precision_doc, 4),
            "average_ndcg_doc": round(avg_ndcg_doc, 4),
            "average_recall_chunk": round(avg_recall_chunk, 4),
            "average_precision_chunk": round(avg_precision_chunk, 4),
            "average_ndcg_chunk": round(avg_ndcg_chunk, 4),
            "failed_row_ids": failures,
            "passed_row_ids": [r["row_id"] for r in evaluated_rows if r["status"] == "PASS"]
        },
        # "details": evaluated_rows  # Removed to prevent LLM token limit errors. Full results are in the Excel file.
    }
