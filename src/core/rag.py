import json
from dataclasses import dataclass
from typing import List
import numpy as np
import faiss
import google.generativeai as genai
from src.config import (
    EMBED_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    MIN_SIMILARITY,
    TOP_K,
)

INDEX_PATH = "indexes/faiss.index"
META_PATH = "indexes/meta.jsonl"

@dataclass
class AnswerResult:
    text: str
    sources: List[dict]
    strategy: str
    score: float = 0.0

class RAGEngine:
    def __init__(self):
        assert GEMINI_API_KEY, "GOOGLE_API_KEY missing in environment"
        genai.configure(api_key=GEMINI_API_KEY)
        try:
            self.index = faiss.read_index(INDEX_PATH)
            self.metas = [json.loads(l) for l in open(META_PATH, "r", encoding="utf-8")]
            self.model = genai.GenerativeModel(GEMINI_MODEL)

            # Tạo cache id -> text để truy xuất nhanh
            self._id2text = {}
            with open("data/processed/chunks.jsonl", "r", encoding="utf-8") as f:
                for line in f:
                    rec = json.loads(line)
                    self._id2text[rec["id"]] = rec["text"]
        except FileNotFoundError:
            print("LỖI: Không tìm thấy file index hoặc chunks. Vui lòng chạy `ingest.py` và `build_index.py` trước.")
            import sys
            sys.exit(1)

    def embed(self, text: str):
        """Nhúng một câu hỏi (query) sử dụng task_type phù hợp."""
        try:
            resp = genai.embed_content(
                model=EMBED_MODEL,
                content=text,
                task_type="RETRIEVAL_QUERY"
            )
            vec = np.array(resp["embedding"], dtype="float32")
            vec /= (np.linalg.norm(vec) + 1e-12)
            return vec
        except Exception as e:
            print(f"Lỗi khi nhúng câu hỏi: {e}")
            return np.zeros(768, dtype="float32") # Kích thước vector của text-embedding-004

    def retrieve(self, query: str, top_k: int = TOP_K):
        q = self.embed(query).reshape(1, -1)
        if np.all(q == 0):
            return []
            
        sims, idxs = self.index.search(q, top_k)
        idxs = idxs[0].tolist()
        sims = sims[0].tolist()
        
        results = []
        for i, s in zip(idxs, sims):
            if i < 0 or i >= len(self.metas):
                continue
            meta = self.metas[i]
            results.append({
                "id": meta["id"],
                "source": meta["source"],
                "section": meta.get("section", ""),
                "score": float(s),
                "text": self._id2text.get(meta["id"], "").strip()
            })
        return results

    def answer(self, question: str) -> AnswerResult:
        contexts = self.retrieve(question, top_k=TOP_K)
        
        top_score = contexts[0].get("score", 0.0) if contexts else 0.0

        has_reliable_context = (
            bool(contexts)
            and contexts[0].get("text", "").strip()
            and top_score >= MIN_SIMILARITY
        )

        if has_reliable_context:
            context_block = "\n\n".join(
                [
                    f"Trích dẫn {i+1} (từ [{c['source']} - {c['id']}]):\n---\n{c['text']}\n---"
                    for i, c in enumerate(contexts)
                ]
            )

            # --- THAY ĐỔI QUAN TRỌNG NHẤT NẰM Ở ĐÂY ---
            system_prompt = (
                "Bạn là ChemA, một trợ lý Hóa học THPT chuyên nghiệp và thân thiện. "
                "Nhiệm vụ của bạn là tổng hợp thông tin từ các tài liệu tham khảo được cung cấp để đưa ra một câu trả lời **hoàn chỉnh, tự nhiên và dễ hiểu** cho học sinh."
            )

            prompt = f"""{system_prompt}

Dưới đây là các trích dẫn từ sách giáo khoa:
{context_block}

Dựa **chủ yếu** vào các trích dẫn trên, hãy soạn một câu trả lời mạch lạc và đầy đủ để trả lời câu hỏi sau. 
**QUAN TRỌNG:** Đừng chỉ sao chép lại nội dung từ các trích dẫn. Hãy diễn giải, giải thích và sắp xếp lại thông tin một cách logic như một giáo viên thực thụ. Nếu thông tin không đủ, hãy nói rằng tài liệu không đề cập rõ và bổ sung kiến thức phổ thông (nếu bạn chắc chắn).

Câu hỏi: "{question}"

Câu trả lời của bạn:
"""

            resp = self.model.generate_content(prompt)
            answer_text = (resp.text or "").strip()
            return AnswerResult(answer_text, contexts, "rag", float(top_score))

        # Fallback khi không có ngữ cảnh đáng tin cậy (giữ nguyên)
        fallback_prompt = f"""Bạn là trợ lý Hóa học THPT thân thiện.
Hãy trả lời bằng tiếng Việt, dựa trên kiến thức phổ thông của bạn.

Câu hỏi: {question}
"""

        resp = self.model.generate_content(fallback_prompt)
        answer_text = (resp.text or "").strip()
        return AnswerResult(answer_text, [], "model", float(top_score))