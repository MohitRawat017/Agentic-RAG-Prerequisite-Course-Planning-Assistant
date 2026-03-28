import json
import os

folder = r"d:\vs code\Assisnment\data\processed"
files = ["full_cleaned_documents.json", "clean_policy.json", "clean_program.json"]

total_words = 0

print("--- Word Count Validation ---")
for file_name in files:
    path = os.path.join(folder, file_name)
    if not os.path.exists(path):
        print(f"❌ '{file_name}' not found.")
        continue
        
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
            # To get an accurate word count of the actual content, we calculate 
            # the length of the stringified json values only, rather than the raw 
            # JSON file which includes thousands of curly braces and keys.
            if isinstance(data, list):
                text_corpus = " ".join([str(v) for obj in data for v in obj.values() if isinstance(v, str)])
            elif isinstance(data, dict):
                text_corpus = " ".join([str(v) for v in data.values() if isinstance(v, str)])
            else:
                text_corpus = str(data)
                
            word_count = len(text_corpus.split())
            total_words += word_count
            print(f"✅ {file_name}: {word_count} words")
            
    except Exception as e:
        print(f"❌ Error processing {file_name}: {e}")

print("-----------------------------")
print(f"🎯 Total Dataset Word Count: {total_words} words")
print("-----------------------------")
