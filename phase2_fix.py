"""
Phase 2 Fix Script: Re-clean and improve classification quality
Addresses mis-classification issues identified in quality review.
"""

import json
import re
import os
from uuid import uuid4
from typing import Optional, Dict
from langchain_core.documents import Document
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv

load_dotenv()

# Input/output paths
INPUT_FILE = "data/processed_catalog/cleaned_documents.json"
OUTPUT_FILE = "data/processed_catalog/cleaned_documents_fixed.json"

# Improved regex patterns (more precise for WCU catalog)
COURSE_PATTERN = re.compile(
    r'([A-Z]{2,4})\s*(\d{3,4})\s*[-–—]\s*([A-Za-z].+?)(?=\n[A-Z]{2,4}\s*\d{3,4}|\Z)',
    re.IGNORECASE | re.DOTALL
)

PROGRAM_PATTERN = re.compile(
    r'(B\.S\.|B\.A\.|Minor|Certificate|Concentration|Major Requirements|Program Requirements)',
    re.IGNORECASE
)

POLICY_PATTERN = re.compile(
    r'(Grading|Academic Standing|Academic Integrity|Course Policies|Prerequisites|Co-requisites|'
    r'Transfer Credits|Repeats|Credit Limits|Instructor Consent)',
    re.IGNORECASE
)

# LlamaParse error patterns to detect and remove
ERROR_PATTERNS = [
    r"I'm sorry, but I cannot extract",
    r"non-text format",
    r"appears to be an image",
    r"cannot process this document",
]

# Initialize Groq LLM for fallback classification
try:
    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0,
        api_key=os.getenv("GROQ_API_KEY")
    )

    classification_prompt = ChatPromptTemplate.from_template(
        "Classify this university catalog excerpt into exactly one category. "
        "Return ONLY one word: course, program_requirement, academic_policy, or general.\n\n"
        "Excerpt:\n{text}\n\nCategory:"
    )

    classification_chain = classification_prompt | llm
    LLM_AVAILABLE = True
    print("✓ Groq LLM initialized for fallback classification")
except Exception as e:
    print(f"⚠️  Groq LLM not available: {e}")
    print("  Continuing with regex-only classification")
    LLM_AVAILABLE = False


def contains_error_message(text: str) -> bool:
    """Check if text contains LlamaParse error messages."""
    for pattern in ERROR_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def strong_clean_text(text: str) -> str:
    """Apply stronger cleaning to remove noise."""
    # Remove headers/footers
    text = re.sub(
        r'West Chester University.*2025-2026.*Catalog|Page \d+ of \d+',
        '',
        text,
        flags=re.IGNORECASE
    )

    # Remove table of contents patterns
    text = re.sub(r'Table of Contents|Course Descriptions|Prerequisites.*Details not provided', '', text, flags=re.IGNORECASE)

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)

    return text.strip()


def classify_with_llm(text: str) -> Optional[str]:
    """Use LLM to classify ambiguous sections."""
    if not LLM_AVAILABLE:
        return None

    try:
        # Limit text to first 1200 characters for efficiency
        text_sample = text[:1200]
        result = classification_chain.invoke({"text": text_sample})
        category = result.content.strip().lower()

        # Validate category
        valid_categories = ["course", "program_requirement", "academic_policy", "general"]
        if category in valid_categories:
            return category
        return None
    except Exception as e:
        print(f"  LLM classification failed: {e}")
        return None


def fix_document(doc: Document) -> Optional[Document]:
    """
    Fix and reclassify a single document.

    Returns:
        Fixed Document or None if document should be dropped
    """
    text = doc.page_content.strip()

    # Drop documents with error messages
    if contains_error_message(text):
        return None

    # Apply strong cleaning
    text = strong_clean_text(text)

    # Skip if too short after cleaning
    if len(text) < 50:
        return None

    # Try regex classification first (more reliable for clear cases)
    section_type = None
    course_code = None

    # Check for course pattern in first 800 chars (where course codes typically appear)
    course_match = COURSE_PATTERN.search(text[:800])
    if course_match:
        # Validate it's a real course code (not "in2021" garbage)
        prefix = course_match.group(1).upper()
        number = course_match.group(2)

        # Course codes should be 2-4 letters followed by 3-4 digits
        if len(prefix) >= 2 and len(number) >= 3 and prefix.isalpha():
            section_type = "course"
            course_code = f"{prefix} {number}"

    # Check for program pattern
    if not section_type and PROGRAM_PATTERN.search(text):
        section_type = "program_requirement"

    # Check for policy pattern
    if not section_type and POLICY_PATTERN.search(text):
        section_type = "academic_policy"

    # Fallback to LLM classification for ambiguous cases
    if not section_type and LLM_AVAILABLE:
        llm_category = classify_with_llm(text)
        if llm_category:
            section_type = llm_category

    # Final fallback
    if not section_type:
        section_type = "general"

    # Build new metadata
    metadata = {
        "source_url": "https://catalog.wcupa.edu/pdf/2025-2026-undergraduate.pdf",
        "accessed_date": "28 March 2026",
        "page_number": doc.metadata.get("page_number"),
        "section_type": section_type,
        "course_code": course_code,
        "document_id": str(uuid4()),
        "document_title": "West Chester University Undergraduate Catalog 2025-2026",
        "section_type_fallback": section_type == "general"
    }

    return Document(page_content=text, metadata=metadata)


def main():
    print("=" * 50)
    print("PHASE 2 FIX: Re-cleaning and Reclassification")
    print("=" * 50)
    print()

    # Load existing documents
    print(f"Loading documents from {INPUT_FILE}...")
    if not os.path.exists(INPUT_FILE):
        raise FileNotFoundError(f"Input file not found: {INPUT_FILE}")

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    original_docs = [
        Document(page_content=item["page_content"], metadata=item["metadata"])
        for item in data
    ]

    print(f"✓ Loaded {len(original_docs)} documents")
    print()

    # Apply fixes
    print("Applying fixes...")
    fixed_docs = []
    dropped_count = 0

    for i, doc in enumerate(original_docs):
        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1}/{len(original_docs)} documents...")

        fixed_doc = fix_document(doc)
        if fixed_doc:
            fixed_docs.append(fixed_doc)
        else:
            dropped_count += 1

    print(f"✓ Fixed {len(fixed_docs)} documents")
    print(f"  Dropped {dropped_count} documents (errors/noise)")
    print()

    # Save fixed documents
    print(f"Saving to {OUTPUT_FILE}...")
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    output_data = [
        {
            "page_content": doc.page_content,
            "metadata": doc.metadata
        }
        for doc in fixed_docs
    ]

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"✓ Saved to {OUTPUT_FILE}")
    print()

    # Show statistics
    print("=" * 50)
    print("FIX STATISTICS")
    print("=" * 50)

    section_counts = {}
    for doc in fixed_docs:
        section_type = doc.metadata.get("section_type", "unknown")
        section_counts[section_type] = section_counts.get(section_type, 0) + 1

    print(f"\nTotal documents: {len(fixed_docs)}")
    print(f"Dropped: {dropped_count}")
    print(f"\nBy section type:")
    for section_type, count in sorted(section_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / len(fixed_docs) * 100) if len(fixed_docs) > 0 else 0
        print(f"  {section_type}: {count} ({percentage:.1f}%)")

    # Course code validation
    course_codes = set()
    for doc in fixed_docs:
        if doc.metadata.get("course_code"):
            course_codes.add(doc.metadata["course_code"])

    print(f"\nUnique course codes: {len(course_codes)}")
    if course_codes:
        sample_codes = sorted(list(course_codes))[:10]
        print(f"Sample codes: {', '.join(sample_codes)}")

    print()
    print("✅ Phase 2 fix complete!")
    print(f"\n Next steps:")
    print(f"  1. Review {OUTPUT_FILE}")
    print(f"  2. If quality looks good, rename to cleaned_documents.json")
    print(f"  3. Re-run report generation: python -m src.ingestion.report")


if __name__ == "__main__":
    main()
