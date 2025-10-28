import os
import sys
from datetime import datetime
from typing import Optional

import streamlit as st
from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.core.math_engine import balance_equation, hint_stoichiometry
from src.core.rag import RAGEngine

load_dotenv()

st.set_page_config(
    page_title="ChemA – Trợ lý Hóa học",
    page_icon="⚛️",
    layout="wide",
)

st.markdown(
    """
    <style>
    .hero-card {
        background: linear-gradient(135deg, #f0f9ff, #d8f3ff);
        border-radius: 1.2rem;
        padding: 1.5rem 1.8rem;
        margin-bottom: 1.2rem;
        border: 1px solid rgba(14, 116, 144, 0.12);
        box-shadow: 0 12px 40px rgba(14, 116, 144, 0.15);
    }
    .hero-card h2 {
        margin: 0 0 0.5rem 0;
        color: #0f172a;
    }
    .hero-card ul {
        margin: 0.4rem 0 0 1.2rem;
        color: #0f172a;
    }
    [data-testid="stChatMessage"] p {
        font-size: 1.05rem;
        line-height: 1.65;
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #ffffff 0%, #e0f2fe 120%);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if "engine" not in st.session_state:
    try:
        st.session_state.engine = RAGEngine()
    except AssertionError as e:
        st.error(f"Lỗi cấu hình RAGEngine: {e}")
        st.stop()
    except FileNotFoundError:
        st.error(
            "Lỗi: Không tìm thấy file index hoặc chunks. Vui lòng chạy `python -m src.ingest` và `python -m src.build_index` trước khi chạy app."
        )
        st.stop()
    except Exception as e:
        st.error(f"Lỗi không xác định khi khởi tạo RAGEngine: {e}")
        import traceback
        st.error(traceback.format_exc())
        st.stop()

engine: RAGEngine = st.session_state.engine

if "turns" not in st.session_state:
    st.session_state.turns = []

st.session_state.messages = []
for turn in st.session_state.turns:
    st.session_state.messages.append({"role": "user", "content": turn.get("question", "")})
    assistant_msg = {"role": "assistant", "content": turn.get("answer", "")}
    if turn.get("footnote"):
        assistant_msg["footnote"] = turn["footnote"]
    st.session_state.messages.append(assistant_msg)


st.title("⚛️ ChemA – Trợ lý Hóa học THPT")
st.markdown(
    """
    <div class="hero-card">
        <h2>Xin chào! 👋</h2>
        <p>ChemA chatbot tra cứu kiến thức hoá học dành cho học sinh THPT từ lớp 10 đến lớp 12</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### 💬 Phiên trò chuyện")
    st.caption("Các hội thoại chỉ được lưu trong phiên làm việc hiện tại.")

    st.markdown("---")
    st.markdown("### Mẹo sử dụng")
    st.markdown(
        "- Gõ `A + B -> C` để cân bằng phương trình tức thì.\n"
        "- Ví dụ Fe + O2 -> Fe2O3\n"
        "- Hỏi về lý thuyết, bài tập, khái niệm trong chương trình 10–12.\n"
        "- Thêm ngữ cảnh cụ thể (chương, bài) để câu trả lời chính xác hơn."
    )

for msg in st.session_state.messages:
    bubble = st.chat_message(msg["role"])
    bubble.write(msg["content"])
    if msg.get("footnote"):
        bubble.caption(msg["footnote"])

def _store_turn(question: str, answer: str, metadata: dict, footnote: Optional[str] = None) -> None:
    timestamp = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    turn_entry = {
        "timestamp": timestamp,
        "question": question,
        "answer": answer,
    }
    if metadata:
        turn_entry["metadata"] = metadata
    if footnote:
        turn_entry["footnote"] = footnote

    st.session_state.turns.append(turn_entry)

prompt = st.chat_input("Nhập câu hỏi hoặc phương trình phản ứng...")

if prompt:
    user_message = {"role": "user", "content": prompt}
    st.session_state.messages.append(user_message)
    st.chat_message("user").write(prompt)

    if "->" in prompt or "→" in prompt:
        try:
            response_text = balance_equation(prompt.replace("→", "->"))
            assistant = st.chat_message("assistant")
            assistant.write(response_text)
            assistant.caption("⚖️ Đã cân bằng phương trình. Dưới đây là một số hằng số cần nhớ.")
            with assistant.expander("Gợi ý tính nhanh"):
                for line in hint_stoichiometry().split("\n"):
                    st.markdown(line)

            assistant_message = { 
                "role": "assistant",
                "content": response_text,
                "footnote": "⚖️ Cân bằng phương trình hóa học.",
            }
            st.session_state.messages.append(assistant_message)
            metadata = {"strategy": "balance"}
            _store_turn(prompt, response_text, metadata, assistant_message.get("footnote"))

        except Exception as e:
            error_message = "Đã xảy ra lỗi khi cố gắng cân bằng phương trình, vui lòng kiểm tra lại cú pháp."
            st.chat_message("assistant").error(error_message) 
            print(f"Lỗi cân bằng phương trình: {e}") 
            assistant_message = {"role": "assistant", "content": error_message} 
            st.session_state.messages.append(assistant_message)
            metadata = {"strategy": "balance_error", "error": str(e)}
            _store_turn(prompt, error_message, metadata)

    else:
        answer_text = "" 
        result = None
        metadata = {}
        
        try: 
            with st.spinner("Đang phân tích..."):
                result = engine.answer(prompt) 
            
            answer_text = result.text or "Mình chưa chắc, bạn thử diễn đạt chi tiết hơn nhé!"
            assistant = st.chat_message("assistant")
            assistant.write(answer_text)

            assistant_message = {
                "role": "assistant",
                "content": answer_text,
                "footnote": (
                    "📚 Chúc bạn học tập hiệu quả"
                ),
            }
            
            if result:
                metadata = {
                    "strategy": result.strategy,
                    "top_score": result.score,
                    "sources": [
                        {
                            "id": s.get("id", ""), 
                            "source": s.get("source", ""),
                            "section": s.get("section"),
                            "score": s.get("score", 0.0),
                        }
                        for s in result.sources
                    ] 
                    if result.sources
                    else [],
                }

        except Exception as e:
            error_message = "Đã xảy ra lỗi, vui lòng thử lại."
            st.chat_message("assistant").error(error_message) 
            print(f"Lỗi trong engine.answer: {e}") 
            import traceback
            traceback.print_exc()
            
            answer_text = error_message
            assistant_message = {"role": "assistant", "content": error_message}
            metadata = {"strategy": "error", "error": str(e)}

        if 'assistant_message' in locals():
            st.session_state.messages.append(assistant_message)
            _store_turn(prompt, answer_text, metadata, assistant_message.get("footnote"))
        else:
            print("Lỗi: assistant_message không được định nghĩa.")
