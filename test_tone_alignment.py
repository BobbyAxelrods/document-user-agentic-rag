import os
import sys
import csv
from dotenv import load_dotenv

# Add the project root to sys.path
sys.path.append(os.getcwd())

from rag.tools.tone_management.tone_tools import classify_tone_group, get_tone_guidelines_by_group, apply_tone_guidelines

def test_tone_flow(query, expected_group=None, expected_pattern=None):
    print(f"\n=== TESTING QUERY: {query} ===")
    if expected_group:
        print(f"Expected Group: {expected_group}")
    
    # 1. Classify
    group = classify_tone_group(query)
    print(f"Detected Group: {group}")
    
    # 2. Get Guidelines
    guidelines = get_tone_guidelines_by_group(group)
    
    # 3. Apply Tone
    factual_context = ""
    citations = None
    if "file a claim" in query.lower():
        factual_context = "To file a claim, log in to the app, select 'Claims', and upload your receipt."
        citations = "Prudential Claims Guide 2024, Page 12"
    elif "physical therapy" in query.lower():
        factual_context = "Your plan covers up to 20 sessions of physical therapy per year."
        citations = "PRUHealth Policy Document v2, Section 4.5"
    elif "blood pressure" in query.lower():
        factual_context = "Blood pressure readings of 140/90 could indicate high blood pressure."
        citations = "Medical Guidelines 2024 - Hypertension Section"
    
    response = apply_tone_guidelines(factual_context, guidelines, query, citations=citations)
    print("--- RESPONSE ---")
    print(response)
    if expected_pattern:
        print(f"\n[Verification Target: {expected_pattern}]")
    print("----------------")

if __name__ == "__main__":
    load_dotenv()
    
    csv_path = r"c:\Users\muhammad.s.safian\OneDrive - Avanade\Project\MAIN_PROJECT\_avanade_main\_avanade_main\_01_prudential\PRUHK-AgenticRAG-V4\rag\tools\tone_management\tone_verification_testcases.csv"
    
    if os.path.exists(csv_path):
        with open(csv_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                test_tone_flow(
                    row['Query'], 
                    expected_group=row['Tone Group'], 
                    expected_pattern=row['Expected Response Pattern (Peace-of-Mind Formula)']
                )
    else:
        print(f"Error: CSV file not found at {csv_path}")
