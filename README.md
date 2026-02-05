# Enterprise Agentic RAG (USER PERSONA)

This project implements an Agentic RAG (Retrieval-Augmented Generation) system for enterprise, designed to manage the lifecycle of enterprise documents and orchestrate RAG queries with Golden Dialogue tone refinement.

## 🚀 Features

 - **Automated Evaluation**: Run regression tests using Excel-based ground truth data (`automated_evaluation_testcase`).
- **Dual-Mode Operation**: Supports both Google Gemini (Sandbox) and Azure OpenAI (Production) via LiteLLM.
- **Tone Refinement**: Ensures responses adhere to "Golden Dialogue" principles (clear, empathetic, professional).
- **Query Corpus** : Query the corpus and get the citation 

## 🛠️ Prerequisites

- **Python**: 3.10 or higher
- **Google Cloud SDK**: Installed and authenticated (`gcloud auth login`, `gcloud auth application-default login`).
- **Vertex AI**: Enabled on your Google Cloud Project.

## 📦 Installation

1.  **Clone the repository** (if not already done).

2.  **Create and activate a virtual environment**:
    ```bash
    python -m venv venv
    # Windows
    .\venv\Scripts\activate
    # macOS/Linux
    source venv/bin/activate
    ```

3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## ⚙️ Configuration

1.  **Environment Variables**: Create a `.env` file in the project root. You can use the following template:

    ```ini
    # Google Cloud
    GOOGLE_CLOUD_PROJECT=your-project-id
    LOCATION=asia-east1
    
    # RAG Configuration
    SANDBOX=false  # Set to true to use Gemini (Sandbox mode), false for Azure OpenAI
    
    # Azure OpenAI (Required if SANDBOX=false)
    AZURE=azure/gpt-4o  # Model name for LiteLLM
    AZURE_API_KEY=your-azure-api-key
    AZURE_API_BASE=https://your-resource.openai.azure.com/
    AZURE_API_VERSION=2024-02-15-preview
    ```

2.  **Google Cloud Authentication**:
    Ensure your local environment is authenticated:
    ```bash
    gcloud config set project your-project-id
    gcloud auth application-default login
    ```

## 🏃 Usage

### Running the Agent

The agent is defined in `rag/agents.py`. You can run it using the Google ADK CLI or your preferred runner.

### Key Workflows

#### 1. Document Ingestion (Staging)
Upload documents to the staging environment for processing and indexing. 
- **Command**: "I want to upload `path/to/policy.pdf`"
- **Agent Action**: validtes file, uploads to GCS Staging bucket, and ingests into Staging Corpus.

#### 2. Automated Regression Testing
Run validation against a set of test cases defined in an Excel file.
- **Command**: "Run automated evaluation on `path/to/testcase.xlsx`"
- **Note**: Provide the **full file path** in the chat. Do not use the file attachment feature for this specific tool to ensure the path is correctly passed to the local file reader.
- **Output**: Generates a report with Pass/Fail status and scores based on ground truth comparison.


## 📁 Project Structure

```
ENTERPRISE-AgenticRAG-V4/
├── rag/
│   ├── agents.py           # Main agent definition and initialization
│   ├── config.py           # Configuration constants (Bucket names, Project ID)
│   ├── instruction.md      # System instructions for the agent
│   └── tools/              # Agent tools
│       ├── corpus/         # Vector Search corpus management
│       ├── lifecycle/      # Lifecycle workflows (Upload, Eval, Promote)
│       ├── storage/        # GCS bucket operations
│       └── tone_management/# Tone refinement logic
├── .env                    # Environment variables (GitIgnored)
├── .gitignore              # Git ignore rules
├── requirements.txt        # Python dependencies
└── regression_test.xlsx    # Sample regression test file
```

## 📝 Developer Notes

- **LiteLLM Integration**: The project uses LiteLLM to bridge calls to Azure OpenAI. Ensure your Azure credentials are correct in `.env`.
- **File Handling**: The `automated_evaluation_testcase` tool reads files from the local filesystem. Ensure the agent has read permissions for the specified file paths.
