import json
import re
from pathlib import Path
from typing import List
import os

from tqdm import tqdm
from docx import Document as DocxDocument
# Thêm các import cần thiết cho việc xử lý cấu trúc docx
from docx.document import Document as _Document
from docx.table import Table
from docx.text.paragraph import Paragraph

# LangChain imports
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_core.documents import Document

# Import config từ thư mục src
try:
    from src.config import CHUNK_OVERLAP, CHUNK_SIZE
except ImportError:
    print("Cảnh báo: Không tìm thấy src.config. Sử dụng giá trị mặc định.")
    CHUNK_SIZE = 2000
    CHUNK_OVERLAP = 200

# Các thư mục lớp (giữ nguyên)
RAW_DIRS = [Path("data/raw/lop10"), Path("data/raw/lop11"), Path("data/raw/lop12"), Path("data/raw/quizz")]
OUT_PATH = Path("data/processed/chunks.jsonl")

def docx_to_markdown_text(doc: _Document) -> str:
    """
    Chuyển đổi đối tượng Document của python-docx sang chuỗi Markdown một cách đáng tin cậy,
    sử dụng các phương thức public API.
    """
    md_lines = []
    # doc.iter_inner_content() duyệt qua các thành phần (đoạn văn, bảng) theo đúng thứ tự
    for block in doc.iter_inner_content():
        if isinstance(block, Paragraph):
            text = block.text.strip()
            # Bỏ qua các đoạn văn trống
            if not text:
                continue
            
            style = block.style.name
            if style.startswith('Heading 1'):
                md_lines.append(f"# {text}")
            elif style.startswith('Heading 2'):
                md_lines.append(f"## {text}")
            elif style.startswith('Heading 3'):
                md_lines.append(f"### {text}")
            elif style.startswith('Heading 4'):
                md_lines.append(f"#### {text}")
            elif style.startswith('Heading 5'):
                md_lines.append(f"##### {text}")
            else:
                md_lines.append(text)
        elif isinstance(block, Table):
            # Chuyển bảng sang định dạng Markdown
            if not block.rows:
                continue
            header_cells = block.rows[0].cells
            md_lines.append("| " + " | ".join(cell.text.strip() for cell in header_cells) + " |")
            md_lines.append("|" + "---|" * len(header_cells))
            for row in block.rows[1:]:
                md_lines.append("| " + " | ".join(cell.text.strip() for cell in row.cells) + " |")
    
    return "\n\n".join(md_lines)

# ==== MAIN ====
def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
        ("####", "Header 4"),
    ]
    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on, strip_headers=False)

    all_chunks: List[Document] = []

    for folder in RAW_DIRS:
        print(f"Đang xử lý thư mục: {folder.name}")
        if not folder.is_dir():
            print(f"Cảnh báo: Thư mục {folder} không tồn tại.")
            continue

        file_paths = list(folder.rglob("*.docx"))
        if not file_paths:
            print(f"Không tìm thấy file .docx nào trong {folder}")
            continue

        for fp in tqdm(file_paths, desc=f"Loading files từ {folder.name}"):
            try:
                # 1. Đọc file .docx bằng python-docx
                doc = DocxDocument(fp)
                
                # 2. Chuyển sang văn bản Markdown
                md_text = docx_to_markdown_text(doc)
                if not md_text.strip():
                    continue

                # 3. Tách theo cấu trúc tiêu đề
                chunks = markdown_splitter.split_text(md_text)
                
                # Thêm source file vào metadata cho mỗi chunk
                for chunk in chunks:
                    chunk.metadata['source'] = str(fp)
                
                all_chunks.extend(chunks)

            except Exception as e:
                print(f"Lỗi khi xử lý file {fp}: {e}")
                import traceback
                traceback.print_exc()

    # Ghi tất cả các chunk vào file jsonl
    print(f"\nTổng cộng {len(all_chunks)} chunks. Đang ghi vào {OUT_PATH}...")
    with open(OUT_PATH, "w", encoding="utf-8") as wf:
        raw_base_path = Path('data/raw')
        for idx, chunk in enumerate(tqdm(all_chunks, desc="Ghi chunks")):
            
            metadata = chunk.metadata
            source_path_str = metadata.get("source", "unknown_source")
            source_path = Path(source_path_str)
            
            try:
                relative_source = source_path.relative_to(raw_base_path)
            except ValueError:
                relative_source = source_path.name
                
            section_parts = []
            for i in range(1, 5):
                header_key = f"Header {i}"
                if header_key in metadata:
                    section_parts.append(metadata[header_key])
            section_str = " > ".join(section_parts)

            chunk_id = f"{relative_source}:{idx}"
            
            # Giữ lại tiêu đề trong nội dung chunk để có ngữ cảnh tốt hơn
            # Splitter đã làm việc này với strip_headers=False
            page_content = chunk.page_content.strip()

            rec = {
                "id": chunk_id,
                "text": page_content,
                "source": str(relative_source),
                "section": section_str,
            }
            wf.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Đã ghi tất cả chunks vào: {OUT_PATH}")

if __name__ == "__main__":
    # Cài đặt: pip install python-docx langchain-text-splitters tqdm
    main()

