# MOLy – Trợ lý Hóa học THPT (RAG + Gemini Pro)

Trợ lý Hóa học cấp 3 dùng **RAG** (Retrieval-Augmented Generation) với **Google Gemini Pro** để trả lời mọi câu hỏi dựa trên nội dung SGK/đề cương, và **math engine** để cân bằng phương trình + tính toán hóa học.

## Tính năng
- RAG: tìm đoạn SGK liên quan (vector search FAISS) → Gemini tổng hợp trả lời và **trích dẫn nguồn**.
- Math engine: cân bằng phương trình (`chempy`), tính mol/khối lượng/thể tích (deterministic).
- Giao diện **Streamlit** (chat UI), sẵn sàng deploy.
- Dùng **Gemini Pro** (`gemini-2.5-pro`) và **Embeddings** (`text-embedding-004`).

## Chuẩn bị
1. Python 3.10+
2. Cài gói:
   ```bash
   pip install -r requirements.txt
   ```
3. Tạo file `.env` từ `.env.example` và điền **GOOGLE_API_KEY** (Gemini).

## Quy trình A → Z
1) **Đặt tài liệu** SGK/đề cương vào `data/raw/` (ưu tiên `.txt`/`.md`/`.docx`. Có hỗ trợ `.pdf` cơ bản).
2) **Ingest & chunk**:
   ```bash
   python -m src.processing.ingest
   ```
   → Tạo `data/processed/chunks.jsonl`

3) **Build index (embeddings + FAISS)**:
   ```bash
   python -m src.processing.build_index
   ```
   → Tạo `indexes/faiss.index` & `indexes/meta.jsonl`

4) **Chạy giao diện**:
   ```bash
   streamlit run app.py
   ```

## Gợi ý dữ liệu mẫu
Đặt file `data/raw/sample_sgk_hoa.txt` (đã kèm mẫu). Bạn có thể thêm nhiều file khác.

## Ghi chú
- Embeddings dùng `text-embedding-004` (1536D). Chúng tôi chuẩn hóa vector và dùng **inner product** với FAISS.
- Với câu hỏi tính toán, `math_engine` sẽ được ưu tiên gọi.
- Khi Gemini không đủ tự tin, câu trả lời sẽ nêu rõ "chưa chắc" và dẫn nguồn gần nhất.

## License
For educational purposes.
