import json
import os

def extract_strings(obj):
    words = 0
    if isinstance(obj, dict):
        for v in obj.values():
            words += extract_strings(v)
    elif isinstance(obj, list):
        for item in obj:
            words += extract_strings(item)
    elif isinstance(obj, str):
        # Count words in the string
        words += len(obj.split())
    elif isinstance(obj, (int, float, bool)):
        # Count primitives as 1 word
        words += 1
    return words

folder = r"d:\vs code\Assisnment\data\processed"
files = ["full_cleaned_documents.json", "clean_policy.json", "clean_program.json"]

total_words = 0

print("--- EXHAUSTIVE RECURSIVE WORD COUNT ---")
for file_name in files:
    path = os.path.join(folder, file_name)
    if not os.path.exists(path):
        print(f"❌ '{file_name}' not found.")
        continue
        
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        word_count = extract_strings(data)
        total_words += word_count
        print(f"📊 {file_name}: {word_count} words")

print("---------------------------------------")
print(f"🎯 Total Dataset Word Count: {total_words} words")
print("---------------------------------------")

# Also print total character count just in case
total_chars = 0
for file_name in files:
    path = os.path.join(folder, file_name)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            total_chars += len(f.read())
print(f"📏 For context, the total FILE SIZE (Characters including JSON syntax): {total_chars} characters")
