import json, urllib.request, os, time, re
from pathlib import Path

# Load key
key = None
with open("/home/haikalthoriqa/RINGKAS/.env") as f:
    for line in f:
        if line.startswith("NVIDIA_NIM_API_KEY="):
            key = line.strip().split("=",1)[1]
            break
if not key:
    raise SystemExit("no key")

dataset_path = Path("/home/haikalthoriqa/RINGKAS/evaluation/evaluation_dataset.json")
dataset = json.loads(dataset_path.read_text(encoding="utf-8"))

# Only improve first 20
for idx in range(20):
    rec = dataset["records"][idx]
    excerpt = rec["evidence"]["excerpt"]
    title = rec["evidence"]["document_title"]
    qtype = rec["question_type"]
    topic = rec["topic"]
    year = rec["evidence"]["publication_year"]
    print(f"[{rec['question_id']}] type {qtype} topic {topic}...")
    # Prompt per type
    type_instruction = {
        "definition": f"Buat pertanyaan bertipe 'definition' yang menanyakan definisi/penjelasan {topic} sesuai dokumen.",
        "number": f"Buat pertanyaan bertipe 'number' yang menanyakan angka/statistik spesifik terkait {topic} (harus ada angka di excerpt).",
        "period": f"Buat pertanyaan bertipe 'period' yang menanyakan periode waktu/tahun data dikumpulkan.",
        "region": f"Buat pertanyaan bertipe 'region' yang menanyakan wilayah fokus dokumen.",
        "methodology": f"Buat pertanyaan bertipe 'methodology' yang menanyakan metodologi pengumpulan data.",
        "document_search": f"Buat pertanyaan bertipe 'document_search' yang menanyakan dokumen mana yang membahas topik tersebut."
    }[qtype]

    user_content = f"""Dokumen: "{title}" tahun {year}
Excerpt (ground truth, maksimal 1500 karakter):
\"\"\"{excerpt[:1200]}\"\"\"

{type_instruction}
Jawaban referensi harus singkat, ter-grounded langsung dari excerpt, dan mengandung angka/periode/wilayah yang tepat jika relevan.
Kembalikan JSON saja dengan format: {{"question": "...", "reference_answer": "..."}}
Jangan tambahkan penjelasan lain di luar JSON."""

    payload = {
        "model": "openai/gpt-oss-120b",
        "messages": [
            {"role": "system", "content": "Kamu adalah generator evaluasi RINGKAS. Selalu kembalikan JSON valid saja."},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.2,
        "max_tokens": 400
    }
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            body = json.load(resp)
            content = body["choices"][0]["message"]["content"]
            # extract json
            m = re.search(r'\{.*\}', content, re.S)
            if m:
                j = json.loads(m.group(0))
                new_q = j.get("question","").strip()
                new_ref = j.get("reference_answer","").strip()
                if new_q and new_ref:
                    rec["question_text"] = new_q
                    rec["reference_answer"] = new_ref
                    print(f"  -> Q: {new_q[:80]}...")
                    print(f"  -> A: {new_ref[:80]}...")
                else:
                    print(f"  -> LLM returned incomplete JSON: {content[:300]}")
            else:
                print(f"  -> No JSON found: {content[:500]}")
    except Exception as e:
        print(f"  Error: {e}")
        try:
            print(e.read().decode()[:1000])
        except: pass
    time.sleep(3)

# Validate and save
from pathlib import Path as P
import sys
sys.path.insert(0, "/home/haikalthoriqa/RINGKAS/services/rag-worker")
from ringkas_worker.evaluation_dataset import EvaluationDataset
try:
    EvaluationDataset.model_validate(dataset)
    print("Validation OK after LLM improvement")
except Exception as e:
    print(f"Validation failed: {e}")
    # try to fix
    raise

dataset_path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Updated {dataset_path}")
