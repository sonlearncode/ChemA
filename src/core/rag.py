import json
from dataclasses import dataclass
from typing import List, Optional, Any, Generator, Dict
import numpy as np
import faiss
import google.generativeai as genai
import PIL.Image
# Bỏ import time nếu không dùng nữa
from google.generativeai.types import GenerationConfig, generation_types, HarmCategory, HarmBlockThreshold

from src.config import (
    EMBED_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    MIN_SIMILARITY,
    TOP_K,
)
from src.core.instructions import SYSTEM_INSTRUCTION
from src.core.text_utils import cleanup_response

INDEX_PATH = "indexes/faiss.index"
META_PATH = "indexes/meta.jsonl"
CHUNKS_PATH = "data/processed/chunks.jsonl"

# Retry helper (dán lên đầu rag.py)
import time, re
from google.api_core import exceptions as gexc

def _sleep_from_error(e, attempt):
    m = re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)", str(e))
    if m:
        time.sleep(max(int(m.group(1)), 2))
    else:
        time.sleep(min(2 ** attempt, 30))  # exponential backoff

def gen_with_retry(model, contents, generation_config, safety_settings, max_tries=5):
    for attempt in range(max_tries):
        try:
            return model.generate_content(
                contents,
                generation_config=generation_config,
                safety_settings=safety_settings,
                stream=True
            )
        except (gexc.ResourceExhausted, gexc.TooManyRequests) as e:  # 429
            _sleep_from_error(e, attempt)
            continue
    raise RuntimeError("Rate limit exceeded after retries")

@dataclass
class StreamOutput:
    """Class để chứa kết quả cuối cùng từ stream, bao gồm metadata."""
    final_text: str
    sources: List[dict]
    strategy: str
    top_score: float

class RAGEngine:
    def __init__(self):
        if not GEMINI_API_KEY:
            raise AssertionError("GOOGLE_API_KEY (hoặc GEMINI_API_KEY) missing in environment")
        genai.configure(api_key=GEMINI_API_KEY)

        self.model = genai.GenerativeModel(
            GEMINI_MODEL,
            system_instruction=SYSTEM_INSTRUCTION
        )

        # Cấu hình an toàn - Sử dụng HarmCategory và HarmBlockThreshold đã import
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }

        # Khởi tạo RAG
        self.index = None
        self.metas = []
        self._id2text = {}
        try:
            self.index = faiss.read_index(INDEX_PATH)
            with open(META_PATH, "r", encoding="utf-8") as f:
                self.metas = [json.loads(line) for line in f]

            with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    rec = json.loads(line)
                    self._id2text[rec["id"]] = rec["text"]
            print("RAG Engine initialized successfully with FAISS index and metadata.")
        except FileNotFoundError:
            print("CẢNH BÁO: Không tìm thấy file index/meta/chunks. Chế độ RAG (tìm kiếm tài liệu) sẽ bị tắt.")
        except Exception as e:
            print(f"Lỗi khi khởi tạo thành phần RAG: {e}")
            import traceback
            traceback.print_exc()

    def embed(self, text: str) -> np.ndarray:
        """Nhúng văn bản (câu hỏi hoặc tài liệu)."""
        try:
            task = "RETRIEVAL_DOCUMENT" if len(text) > 256 else "RETRIEVAL_QUERY"
            resp = genai.embed_content(
                model=EMBED_MODEL,
                content=text,
                task_type=task
            )
            vec = np.array(resp["embedding"], dtype=np.float32)
            norm = np.linalg.norm(vec)
            if norm == 0: return vec
            vec /= norm
            return vec
        except Exception as e:
            print(f"Lỗi khi nhúng văn bản: {e}")
            return np.zeros(768, dtype=np.float32) # Kích thước của text-embedding-004

    def retrieve(self, query: str, top_k: int = TOP_K) -> List[Dict]:
        """Tìm kiếm văn bản trong FAISS (RAG)."""
        if not self.index:
            print("RAG retrieve skipped: Index not loaded.")
            return []
        query_vector = self.embed(query).reshape(1, -1)
        if np.all(query_vector == 0):
            print("RAG retrieve skipped: Query embedding failed.")
            return []
        try:
            distances, indices = self.index.search(query_vector, top_k)
            results = []
            if indices.size > 0:
                for i, dist in zip(indices[0], distances[0]):
                    if 0 <= i < len(self.metas):
                        score = float(dist)
                        if score >= MIN_SIMILARITY:
                            meta = self.metas[i]
                            results.append({
                                "id": meta.get("id", ""),
                                "source": meta.get("source", ""),
                                "section": meta.get("section", ""),
                                "score": score,
                                "text": self._id2text.get(meta.get("id", ""), "").strip()
                            })
            return results
        except Exception as e:
            print(f"Lỗi khi tìm kiếm FAISS: {e}")
            return []

    def answer_stream(self, question: str,
                      uploaded_file: Optional[Any] = None,
                      mode: str = "Bình thường") -> Generator[str, None, StreamOutput]:
        """
        Tạo phản hồi stream từ Gemini, tích hợp RAG hoặc đa phương thức.
        Yields các chunk văn bản đã làm sạch.
        Returns StreamOutput chứa kết quả cuối cùng và metadata khi kết thúc.
        """
        contents = []
        strategy = ""
        sources = []
        top_score = 0.0
        mode_instruction = f"\n[CHẾ ĐỘ HIỆN TẠI: {mode.upper().split('(')[0].strip()}]"
        final_response_text = ""

        # Xử lý Ảnh
        if uploaded_file:
            strategy = "multimodal_vision"
            try:
                img = PIL.Image.open(uploaded_file)
                img.thumbnail((1024, 1024))
                contents.append(img)
                prompt_text = f"{mode_instruction}\n\nYêu cầu của học sinh: \"{question}\"\nHãy phân tích hình ảnh này dựa trên vai trò và hướng dẫn hệ thống của bạn."
                contents.append(prompt_text)
                print(f"Processing image with prompt: {prompt_text}")
            except Exception as e:
                error_msg = f"Lỗi: Không thể xử lý file ảnh. Chi tiết: {e}"
                print(error_msg)
                yield error_msg
                return StreamOutput(final_text=error_msg, sources=[], strategy="error", top_score=0.0)

        # Xử lý Văn bản (RAG hoặc Model Only)
        else:
            contexts = self.retrieve(question, top_k=TOP_K)
            if contexts:
                strategy = "rag"
                sources = contexts
                top_score = contexts[0].get("score", 0.0) if contexts else 0.0
                context_block = "\n\n---\n\n".join([
                    f"Nguồn {idx+1} (score: {c.get('score', 0.0):.2f}):\n{c.get('text', '')}"
                    for idx, c in enumerate(contexts)
                ])
                prompt_text = f"""{mode_instruction}

Thông tin tham khảo từ tài liệu:
---
{context_block}
---
Dựa vào thông tin trên và kiến thức của bạn, hãy trả lời câu hỏi sau một cách tự nhiên, sâu sắc, không đề cập đến "nguồn" hay "trích dẫn".

Câu hỏi: "{question}"
"""
                contents.append(prompt_text)
                print(f"Processing text with RAG. Found {len(contexts)} relevant contexts.")
            else:
                strategy = "model_only"
                prompt_text = f"""{mode_instruction}

(Không tìm thấy thông tin trực tiếp trong tài liệu tham khảo)
Dựa vào kiến thức hóa học phổ thông của bạn, hãy trả lời câu hỏi sau.

Câu hỏi: "{question}"
"""
                contents.append(prompt_text)
                print("Processing text using model's general knowledge (no RAG hits).")

        # Gọi Gemini (Streaming)
        try:
            generation_config = GenerationConfig(
                temperature=0.7,
                top_p=0.95,
                top_k=40,
                max_output_tokens=4096,
            )

            stream = gen_with_retry(
                self.model, contents,
                generation_config=generation_config,
                safety_settings=self.safety_settings,
            )

            # Xử lý stream
            for chunk in stream:
                 if chunk.text:
                    # cleaned_chunk = cleanup_response(chunk.text)
                    cleaned_chunk = cleanup_response(chunk.text, do_exam_layout=True)
                    final_response_text += cleaned_chunk
                    yield cleaned_chunk
                 else:
                    finish_reason = None
                    block_reason = None
                    try:
                        if chunk._result.candidates and chunk._result.candidates[0].finish_reason != generation_types.FinishReason.STOP:
                             finish_reason = chunk._result.candidates[0].finish_reason.name
                    except (IndexError, AttributeError): pass

                    try:
                        if chunk._result.prompt_feedback and chunk._result.prompt_feedback.block_reason:
                            block_reason = chunk._result.prompt_feedback.block_reason.name
                    except AttributeError: pass

                    if block_reason:
                        warning_msg = f"\n\n⚠️ Bị chặn vì: {block_reason}"
                        print(warning_msg)
                        final_response_text += warning_msg
                        yield warning_msg
                    elif finish_reason and finish_reason not in ['STOP', 'FINISH_REASON_UNSPECIFIED']:
                         warning_msg = f"\n\n⚠️ Kết thúc bất thường: {finish_reason}"
                         print(warning_msg)
                         final_response_text += warning_msg
                         yield warning_msg

            print(f"Stream finished. Strategy: {strategy}, Top Score: {top_score}")
            # Đảm bảo trả về StreamOutput ngay cả khi không có lỗi hay cảnh báo
            return StreamOutput(final_text=final_response_text, sources=sources, strategy=strategy, top_score=top_score)

        except Exception as e:
            error_msg = f"Đã xảy ra lỗi khi giao tiếp với AI: {e}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            yield error_msg
            return StreamOutput(final_text=error_msg, sources=[], strategy="error", top_score=0.0)