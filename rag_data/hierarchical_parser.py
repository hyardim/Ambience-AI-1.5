import fitz  # PyMuPDF
import os
import re
import random
import pickle
import numpy as np
import torch
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer, util

# --- CONFIGURATION ---
MODEL_NAME = 'all-MiniLM-L6-v2'
BATCH_SIZE = 128
SIMILARITY_THRESHOLD = 0.30 

# Detect GPU
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"⏳ Loading AI Model on {device.upper()}...")
model = SentenceTransformer(MODEL_NAME, device=device)

# Load Noise Embeddings
NOISE_DESCRIPTIONS = [
    "A list of academic references, citations, and bibliography",
    "A table of contents with page numbers and section titles",
    "A list of authors, committee members, and their affiliations",
    "Financial disclosures, funding sources, and conflict of interest statements",
    "Copyright notices, legal disclaimers, and publishing rights",
    "Indices of tables, figures, or abbreviations",
    "Administrative details about the guideline methodology",
    "Download links and website URLs",
    "Journal metadata, submission dates, and DOIs"
]
noise_embeddings = model.encode(NOISE_DESCRIPTIONS, convert_to_tensor=True)
print("✅ Model Loaded.")

def clean_lines_iterative(full_text):
    """
    Surgical Cleaner: Removes artifacts line-by-line and within lines.
    """
    lines = full_text.split('\n')
    cleaned_lines = []
    
    # --- 1. COMPILED REGEX PATTERNS ---
    
    # Page Headers
    page_regex = re.compile(r'Page\s+\d+(\s+of\s+\d+)?', re.IGNORECASE)
    
    # Rights/Boilerplate
    rights_regex = re.compile(r'notice-of-rights|conditions#|all rights reserved|© nice|© the author', re.IGNORECASE)
    
    # Navigation / Administrative Boilerplate (Fix for Chunk 299/162)
    nav_regex = re.compile(r'(return to recommendation|why the committee made|full details of the evidence|terms used in this guideline|recommendations for research)', re.IGNORECASE)
    
    # Table of Contents Dots (Fix for Chunk 9/12)
    # Matches lines with 4 or more consecutive dots
    toc_regex = re.compile(r'\.{4,}')
    
    # Metadata (DOI, Email, Dates)
    meta_regex = re.compile(r'(doi:\s*10\.\d+|e-mail:\s+\S+|received:\s+\d+|accepted:\s+\d+)', re.IGNORECASE)
    
    # Journal Abbreviations
    journal_regex = re.compile(r'(Ann Rheum Dis|J Rheumatol|Arthritis Care|Clin Rheumatol|Best Pract Res|Int J)', re.IGNORECASE)
    
    # Numbered Citations
    citation_number_regex = re.compile(r'^\s*\[?\d{1,4}\]?\.?\s+[A-Z]')
    
    # Financial Disclosures
    financial_regex = re.compile(r'(received|declaration).*?(honoraria|fee|grant|funding|consultancy)', re.IGNORECASE)
    
    # URL/Link Fragments
    url_regex = re.compile(r'https?://|www\.|accessed on|available at', re.IGNORECASE)
    
    # Orphaned Footnotes (Fix for Chunk 35)
    # Matches "a In the healthy..." or "b If conception..." at start of line
    footnote_regex = re.compile(r'^[a-z]\s+[A-Z]')

    for line in lines:
        line_clean = line.strip()
        if not line_clean: continue

        # --- 2. DESTRUCTIVE REPLACEMENTS ---
        line_clean = page_regex.sub('', line_clean)
        line_clean = meta_regex.sub('', line_clean)
        
        # Remove weird bullet points (Chunk 127)
        line_clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\xff]', ' ', line_clean)
        
        # --- 3. LINE KILLERS ---
        if rights_regex.search(line_clean): continue
        if nav_regex.search(line_clean): continue # Kill navigation text
        if toc_regex.search(line_clean): continue # Kill TOC dots
        if journal_regex.search(line_clean): continue
        if citation_number_regex.match(line_clean): continue
        if financial_regex.search(line_clean): continue
        if url_regex.search(line_clean): continue
        if footnote_regex.match(line_clean) and len(line_clean) < 100: continue # Kill short footnotes
        
        # Table/Figure Headers
        if re.match(r'^(Table|Figure)\s+\d+$', line_clean, re.IGNORECASE): continue

        # Mangled Bibliography
        if re.search(r'[A-Za-z]+\s+[A-Z][,.]?$', line_clean):
            if len(line_clean) < 40: continue

        if len(line_clean.strip()) > 5:
            cleaned_lines.append(line_clean)
        
    return " ".join(cleaned_lines)

def fix_stuttering_headers(text):
    """
    Fixes 'Warfarin Warfarin' issues caused by header merging.
    """
    words = text.split()
    if len(words) > 1 and words[0].lower() == words[1].lower():
        # Remove the first word if it duplicates the second (case-insensitive)
        return " ".join(words[1:])
    return text

def batch_filter_chunks(chunks):
    """
    Aggressive Chunk Filter
    """
    if not chunks: return [], 0
    candidates = []
    skipped_count = 0
    
    for c in chunks:
        # A. Reference/Bibliography Pattern
        if ("et al" in c.lower() or "vol " in c.lower()) and c.count(',') > 3:
            skipped_count += 1
            continue
            
        # B. Digit Density (Strict 12%)
        digit_ratio = sum(char.isdigit() for char in c) / len(c)
        if digit_ratio > 0.12: 
            skipped_count += 1
            continue

        # C. Statistical Table Pattern
        stat_pattern = re.findall(r'\(\d+\.?\d*\)', c)
        if len(stat_pattern) >= 2:
            skipped_count += 1
            continue

        # D. Mangled Table Rows
        if "SOA " in c or "GRADE " in c or "95% CI" in c:
            skipped_count += 1
            continue
        
        # E. Short Fragments
        if len(c) < 50:
            skipped_count += 1
            continue
        
        # Apply Stutter Fix (Chunk 108)
        c = fix_stuttering_headers(c)
            
        candidates.append(c)

    if not candidates: return [], skipped_count

    # AI Filtering
    candidate_embeddings = model.encode(candidates, convert_to_tensor=True, batch_size=BATCH_SIZE, show_progress_bar=False)
    cosine_scores = util.cos_sim(candidate_embeddings, noise_embeddings)
    max_scores, _ = torch.max(cosine_scores, dim=1)
    
    final_valid_chunks = []
    for i, score in enumerate(max_scores):
        if score.item() < SIMILARITY_THRESHOLD:
            final_valid_chunks.append(candidates[i])
        else:
            skipped_count += 1
            
    return final_valid_chunks, skipped_count

def process_all_files():
    base_dir = "rag_data"
    folders = ["NICE", "BSR", "Other"]
    
    all_chunks_for_review = [] 
    pure_chunks_only = []      
    total_valid = 0
    total_skipped = 0
    
    print("\n--- STARTING POLISHED PIPELINE (50 SAMPLE AUDIT) ---\n")

    for folder in folders:
        folder_path = os.path.join(base_dir, folder)
        if not os.path.exists(folder_path): continue
            
        files = [f for f in os.listdir(folder_path) if f.endswith('.pdf')]
        print(f"📂 Processing {folder} ({len(files)} files)...")
        
        for f in files:
            full_path = os.path.join(folder_path, f)
            try:
                # 1. Open
                doc = fitz.open(full_path)
                full_text = ""
                for page in doc:
                    full_text += page.get_text()
                
                # 2. LINE-BY-LINE SCRUBBING
                clean_text = clean_lines_iterative(full_text)
                
                # 3. Split
                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=450,
                    chunk_overlap=100,
                    separators=["\n\n", "\n", ". ", " ", ""]
                )
                raw_chunks = splitter.split_text(clean_text)
                
                # 4. Batch Filter
                valid_chunks, skipped = batch_filter_chunks(raw_chunks)
                
                if valid_chunks:
                    total_valid += len(valid_chunks)
                    total_skipped += skipped
                    for i, c in enumerate(valid_chunks):
                        pure_chunks_only.append(c)
                        all_chunks_for_review.append(f"SOURCE: {f} | CHUNK: {i}\n{c}\n{'-'*40}\n")
                
                print(f"  ✅ {f}: {len(valid_chunks)} chunks (dropped {skipped})")
                    
            except Exception as e:
                print(f"  ❌ Error {f}: {e}")

    # Save Samples
    if all_chunks_for_review:
        sample_size = min(50, len(all_chunks_for_review))
        samples = random.sample(all_chunks_for_review, sample_size)
        with open("sample_review.txt", "w") as f:
            f.write(f"=== SAMPLE AUDIT (POLISHED): {sample_size} CHUNKS ===\n")
            f.write(f"Total Noise Blocked: {total_skipped}\n\n")
            f.writelines(samples)

    # Save Database
    with open("rag_data/all_chunks.pkl", "wb") as f:
        pickle.dump(pure_chunks_only, f)

    print(f"\n--- PIPELINE COMPLETE ---")
    print(f"Final Index Size: {total_valid} chunks")
    print(f"Total Noise Blocked: {total_skipped}")
    print(f"Audit file: 'sample_review.txt'")

if __name__ == "__main__":
    process_all_files()