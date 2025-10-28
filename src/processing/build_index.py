import os
import json
import numpy as np
import faiss
from tqdm import tqdm
import google.generativeai as genai
from typing import List  # <<<--- THÊM DÒNG NÀY ĐỂ FIX LỖI

# Import config từ thư mục src (giữ nguyên)
try:
    from src.config import GEMINI_API_KEY, EMBED_MODEL
except ImportError:
    print("Cảnh báo: Không thể import config. Sử dụng giá trị mặc định.")
    # Cần cung cấp các giá trị này trong file .env
    GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
    EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-004")

CHUNKS_PATH = "data/processed/chunks.jsonl"
INDEX_PATH = "indexes/faiss.index"
META_PATH = "indexes/meta.jsonl"

def load_chunks():
    """Tải các chunk từ file chunks.jsonl."""
    try:
        with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                yield json.loads(line)
    except FileNotFoundError:
        print(f"Lỗi: Không tìm thấy file {CHUNKS_PATH}. Hãy chạy script ingest.py trước.")
        return []

def embed_texts(texts: List[str]) -> np.ndarray:
    """Nhúng tài liệu theo batch sử dụng task_type phù hợp."""
    print(f"Bắt đầu nhúng {len(texts)} chunks...")
    if not texts:
        return np.array([])
        
    try:
        # Quan trọng: Chỉ định task_type là 'RETRIEVAL_DOCUMENT'
        result = genai.embed_content(
            model=EMBED_MODEL,
            content=texts,
            task_type="RETRIEVAL_DOCUMENT"
        )
        
        embeddings = np.array(result['embedding'], dtype="float32")
        
        # Chuẩn hóa (normalize) các vector
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-12
        embeddings = embeddings / norms
        
        print(f"Hoàn thành nhúng. Shape của embeddings: {embeddings.shape}")
        return embeddings

    except Exception as e:
        print(f"Lỗi trong quá trình embedding: {e}")
        raise e

def main():
    """Hàm chính để thực thi việc tạo index."""
    if not GEMINI_API_KEY:
        print("Lỗi: GOOGLE_API_KEY (hoặc GEMINI_API_KEY) chưa được thiết lập trong file .env")
        return
        
    genai.configure(api_key=GEMINI_API_KEY)

    os.makedirs("indexes", exist_ok=True)
    metas = []
    texts = []
    
    print("Loading chunks...")
    chunks_generator = load_chunks()
    if not chunks_generator:
        return

    for rec in tqdm(chunks_generator):
        texts.append(rec["text"])
        metas.append({
            "id": rec["id"],
            "source": rec["source"],
            # Lấy section an toàn hơn với .get()
            "section": rec.get("section", ""),
        })

    # --- CÁC DÒNG CODE NÀY ĐÃ ĐƯỢC CHUYỂN VÀO BÊN TRONG HÀM MAIN ---
    if not texts:
        print("Không có text để embed. Dừng lại.")
        return

    print("Embedding...")
    X = embed_texts(texts)
    
    if X.size == 0:
        print("Embedding thất bại, không tạo index.")
        return
        
    d = X.shape[1]
    index = faiss.IndexFlatIP(d)
    index.add(X)

    print(f"Đang ghi index vào {INDEX_PATH}...")
    faiss.write_index(index, INDEX_PATH)
    
    print(f"Đang ghi metadata vào {META_PATH}...")
    with open(META_PATH, "w", encoding="utf-8") as wf:
        for m in metas:
            wf.write(json.dumps(m, ensure_ascii=False) + "\n")
            
    print(f"Đã lưu index vào {INDEX_PATH} và metadata vào {META_PATH}")

if __name__ == "__main__":
    main()
