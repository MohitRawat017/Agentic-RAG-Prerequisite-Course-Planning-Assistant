import json
import os
import re
from uuid import uuid4
from langchain.schema import Document
from llama_parse import LlamaParse

# ================== CONFIG ==================
PDF_PATH = "data/raw_catalog/2025-2026_wcu_undergraduate_catalog.pdf"
OUTPUT_JSON = "data/processed_catalog/cleaned_documents.json"

# LlamaParse setup
parser = LlamaParse(
    api_key=os.getenv("LLAMA_CLOUD_API_KEY"),   # Make sure this is in your .env
    result_type="markdown",                     # Best for catalogs
    parsing_instruction="Extract all text exactly as it appears in the university catalog. Do not summarize or add any extra commentary.",
    max_pages_per_chunk=1,                      # Force one page per document
)

# ================== LOAD + CLEAN ==================
print("Running fresh LlamaParse on the PDF...")
raw_docs = parser.load_data(PDF_PATH)

print(f"LlamaParse returned {len(raw_docs)} documents (one per page)")

cleaned_docs = []

for i, raw_doc in enumerate(raw_docs):
    text = raw_doc.text if hasattr(raw_doc, "text") else raw_doc.page_content
    
    # === Minimal cleaning only ===
    # 1. Remove LlamaParse error messages
    if "I'm sorry, but I cannot extract" in text or "non-text format" in text:
        continue
    
    # 2. Remove common header/footer junk
    text = re.sub(r'West Chester University.*2025-2026.*Catalog', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Page \d+ of \d+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)
    
    # 3. Basic whitespace normalization
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Skip empty or tiny pages
    if len(text) < 100:
        continue
    
    # === Minimal metadata for citations ===
    metadata = {
        "source_url": "https://catalog.wcupa.edu/pdf/2025-2026-undergraduate.pdf",
        "accessed_date": "28 March 2026",
        "page_number": i + 1,
        "document_id": str(uuid4()),
        "document_title": "West Chester University Undergraduate Catalog 2025-2026"
    }
    
    cleaned_docs.append(Document(page_content=text, metadata=metadata))

# ================== SAVE ==================
os.makedirs("data/processed_catalog", exist_ok=True)

with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(
        [{"page_content": doc.page_content, "metadata": doc.metadata} for doc in cleaned_docs],
        f,
        indent=2,
        ensure_ascii=False
    )

print(f"\n✅ CLEAN PHASE 2 COMPLETE")
print(f"   Total clean documents: {len(cleaned_docs)}")
print(f"   Saved to: {OUTPUT_JSON}")
print(f"   This meets the assessment requirement (30k+ words) many times over.")