# Agentic RAG: Course Planning Assistant

An AI-powered academic advisor designed to operate within a university Learning Management System (LMS). Built using an **Agentic RAG (Retrieval-Augmented Generation)** architecture with LangGraph, this assistant helps students navigate complex university catalogs, verifies course prerequisites, generates term plans, and safely abstains from answering when the required information isn't in the provided materials.

---

## 🚀 Key Capabilities

This system requires high precision and strict grounding to prevent "hallucinated" academic advice. We implemented the following **5 mandatory capabilities**:

1. **Grounded Answers with Citations:** Every single claim is backed by a specific citation (URL and Section/Chunk) from the official university catalog. If it can't be cited, the system won't say it.
2. **Prerequisite Reasoning:** Accurately evaluates prerequisite chains, co-requisites, minimum grade requirements, and program rules to determine if a student is eligible for a course.
3. **Automated Course Planning:** Generates suggested course lists for upcoming terms based on the student's completed courses, target major, and credit constraints—while explaining the justification and any assumptions.
4. **Proactive Clarification:** If critical information is missing (such as catalog year, transfer credits, or intended major), the assistant asks clarifying questions before attempting to build a plan.
5. **Safe Abstention:** When queried about information not found in the catalog (e.g., specific class schedules, professor availability), the system gracefully abstains using a "I don't have that information" message and points the student toward the appropriate resource.

---

## 🏗️ System Architecture

The project utilizes a state-of-the-art **Multi-Agent Graph WorkFlow** powered by **LangGraph**, where specialized nodes execute parts of the reasoning chain:

- `Intake Node`: Extracts the student's profile from the query and determines if enough information is present to proceed, or if clarifying questions must be asked.
- `Retriever Node`: Embeds the query and fetches the most relevant catalog rules, prerequisite tables, and academic policies via **ChromaDB**.
- `Planner Node`: Analyzes retrieved documents against the student's profile to formulate eligibility decisions or a course plan.
- `Verifier Node`: An internal auditing agent that strictly checks the Planner's output to ensure every claim maps to an exact citation. It enforces the "No guess" rule.
- `Formatter Node`: Formats the finalized text into a structured, readable JSON/Markdown payload.

### Tech Stack
- **Frameworks:** LangGraph, LangChain
- **LLM Engine:** Google Gemini (`langchain-google-genai`), Groq fallback
- **Vector Database:** ChromaDB
- **Embeddings:** `sentence-transformers` (Local HuggingFace embeddings)
- **Document Ingestion:** LlamaParse & PyMuPDF
- **Frontend / UI:** Gradio

---

## 📚 Data Source

The RAG system operates over the **West Chester University Undergraduate Catalog 2025-2026**.
- **URL:** [https://catalog.wcupa.edu/pdf/2025-2026-undergraduate.pdf](https://catalog.wcupa.edu/pdf/2025-2026-undergraduate.pdf)
- **Size:** Comprehensive data containing thousands of words, parsed and chunked contextually.
- **Coverage:** Consists of undergraduate course descriptions, program/major requirements, and vital academic policies (grading, credit limits, repeats, instructor consent, etc.).

We utilize a custom parsing pipeline (`src.ingestion`) that uses LlamaParse to clean the chaotic PDF formatting, preserving semantic tables and prerequisite hierarchies, before chunking and embedding.

---

## ⚙️ Setup and Installation

### 1. Requirements
Ensure you have **Python 3.12+** installed on your system. We recommend using `uv` for lightning-fast dependency management.

### 2. Environment Variables
Create a `.env` file in the root directory and populate it with your API keys (see `.env.example`):
```env
LLAMA_CLOUD_API_KEY=your_llamaparse_key_here
GROQ_API_KEY=your_groq_key_here
GEMINI_API_KEY=your_gemini_key_here
```

### 3. Usage
You can launch the interactive Gradio UI to chat with the assistant and inspect the reasoning nodes (Retrieved Chunks, Planner JSON, Verifier JSON) in real-time.

```bash
uv pip install -e .
python -m src.planning.gradio_app
```

---

## 🧪 Evaluation & Testing

A robust test suite (`tests/`) has been created to measure:
- **Citation Coverage Rate:** Percentage of outputs securely grounded by a valid catalog chunk.
- **Eligibility Correctness:** Accuracy on multi-hop prerequisite chaining.
- **Abstention Accuracy:** Preventing hallucinations on trick ("not in docs") questions.

Run the test suite via:
```bash
python -m pytest tests/
```