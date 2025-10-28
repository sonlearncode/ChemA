import os
import sys
from datetime import datetime
from typing import Optional, Generator, Any
import streamlit as st
from dotenv import load_dotenv
import PIL.Image
import io 

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.core.math_engine import balance_equation, hint_stoichiometry
from src.core.rag import RAGEngine, StreamOutput
from src.core.instructions import GREETING_MESSAGE

load_dotenv()


st.set_page_config(
    page_title="ChemA – Trợ lý Hóa học",
    page_icon="⚛️",
    layout="wide",
)

st.markdown(
    """
    <style>
    /* Hero Card */
    .hero-card {
        background: linear-gradient(135deg, #f0f9ff, #d8f3ff);
        border-radius: 1.2rem;
        padding: 1.5rem 1.8rem;
        margin-bottom: 1.2rem;
        border: 1px solid rgba(14, 116, 144, 0.12);
        box-shadow: 0 12px 40px rgba(14, 116, 144, 0.15);
    }
    .hero-card h2 { margin: 0 0 0.5rem 0; color: #0f172a; font-weight: 600; }
    .hero-card p, .hero-card li, .hero-card hr { color: #334155; }
    .hero-card hr { border-top: 1px solid rgba(14, 116, 144, 0.2); margin: 0.8rem 0; }
    .hero-card ul { margin: 0.4rem 0 0 1.2rem; padding-left: 0.5rem; }
    .hero-card li { margin-bottom: 0.3rem; }

    /* Chat Messages */
    [data-testid="stChatMessage"] { padding: 0.8rem 1rem; border-radius: 1rem; margin-bottom: 0.8rem; }
    [data-testid="stChatMessage"] p { font-size: 1.05rem; line-height: 1.65; color: inherit; }
    [data-testid="stChatMessage"]:has(span[title="assistant"]) { background-color: #f1f5f9; color: #1e293b; }
    [data-testid="stChatMessage"]:has(span[title="user"]) { background-color: #3b82f6; color: #ffffff; }
    [data-testid="stChatMessage"] > div:first-child { gap: 0.8rem; }
    /* Avatar styles */
    .stChatMessage .stAvatar img { width: 2.2rem; height: 2.2rem; border-radius: 50%; object-fit: cover; }
    /* Ensure user avatar is on the right */
    [data-testid="stChatMessage"]:has(span[title="user"]) > div:first-child { flex-direction: row-reverse; }

    /* Sidebar */
    [data-testid="stSidebar"] { background: linear-gradient(180deg, #ffffff 0%, #f0f9ff 120%); padding: 1.5rem; }
    [data-testid="stSidebar"] h3 { color: #0c4a6e; margin-top: 1rem; }
    [data-testid="stSidebar"] .stCaption { color: #64748b; }
    [data-testid="stSidebar"] hr { border-top: 1px solid #e2e8f0; }
    .stButton>button { width: 100%; border-radius: 0.5rem; border: 1px solid #ef4444; color: #ef4444; background-color: #fee2e2; margin-top: 0.5rem; }
    .stButton>button:hover { background-color: #fecaca; color: #dc2626; border-color: #dc2626; }
    [data-testid="stSidebar"] .stImage { border-radius: 0.5rem; border: 1px solid #e2e8f0; margin-bottom: 0.5rem; }

    /* Uploaded image preview in chat */
    .uploaded-image-preview { max-width: 300px; max-height: 300px; border-radius: 0.5rem; border: 1px solid #ddd; margin-bottom: 0.5rem; }
    /* Error messages in chat */
    [data-testid="stException"] { background-color: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; border-radius: 0.5rem; padding: 0.8rem 1rem; }
    /* Spinner text */
    .stSpinner > div > div { color: #0c4a6e; font-weight: 500; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Khởi tạo RAGEngine  
@st.cache_resource
def get_rag_engine():
    try:
        engine = RAGEngine()
        print("RAGEngine initialized successfully.")
        return engine
    except AssertionError as e:
        st.error(f"Lỗi cấu hình RAGEngine: {e}")
        st.stop()
    except Exception as e:
        st.error(f"Lỗi nghiêm trọng khi khởi tạo RAGEngine: {e}")
        st.stop()

engine: RAGEngine = get_rag_engine()

# Quản lý Session State  
if "messages" not in st.session_state:
    st.session_state.messages = []
if "turns" not in st.session_state:
    st.session_state.turns = []
if "current_mode" not in st.session_state:
    st.session_state.current_mode = "Bình thường"
if "uploaded_file_data" not in st.session_state:
    st.session_state.uploaded_file_data = None
if "current_file_id" not in st.session_state:
     st.session_state.current_file_id = None


# Giao diện Sidebar (Thanh bên)  
with st.sidebar:
    st.markdown("### ⚛️ ChemA")
    st.caption("Trợ lý Hóa học Đa phương thức")
    st.markdown(" ")

    # Chọn chế độ học
    st.markdown("### 🧠 Chế độ học")
    modes = [
        "Bình thường", "🐢 Học chậm (Chi tiết)", "🚀 Nâng cao (Học sinh giỏi)",
        "⚡ Ôn thi cấp tốc", "💪 Thực hành", "🎮 Giải trí (Sắp có)"
    ]
    st.session_state.current_mode = st.selectbox(
        "Chọn chế độ học:", modes,
        index=modes.index(st.session_state.current_mode), key="mode_select"
    )

    st.markdown(" ")

    # Tải ảnh lên
    st.markdown("### 📸 Tải ảnh lên")
    st.caption("Tải ảnh đề bài, bài làm")
    st.caption("Nhớ gỡ ảnh sau khi dùng xong để tránh nhầm lẫn nhé!")
    uploaded_file = st.file_uploader(
        "Chọn file ảnh (PNG, JPG, JPEG):",
        type=["png", "jpg", "jpeg"],
        key="file_uploader"
    )

    # Xử lý file tải lên
    if uploaded_file:
        # Sử dụng file_id để kiểm tra file mới
        if st.session_state.current_file_id != uploaded_file.file_id:
            st.session_state.uploaded_file_data = uploaded_file
            st.session_state.current_file_id = uploaded_file.file_id
            print(f"File '{uploaded_file.name}' ready.")

        # Hiển thị ảnh đang chờ xử lý (từ state)
        if st.session_state.uploaded_file_data:
             st.image(st.session_state.uploaded_file_data, caption="Ảnh xem trước", use_container_width=True)

    elif st.session_state.current_file_id:
        st.session_state.uploaded_file_data = None
        st.session_state.current_file_id = None


    st.markdown(" ")
    st.markdown("### Mẹo sử dụng")
    st.markdown(
        "- Gõ `A + B -> C` để cân bằng phương trình.\n"
        "- Tải ảnh lên rồi gõ 'Giải bài này'.\n"
        "- Hỏi lý thuyết, bài tập, khái niệm.\n"
        "- Đưa ngữ cảnh hỏi vào sẽ giúp chatbot phản hồi tốt hơn.\n"
    )

# Giao diện Chat chính  
st.title("⚛️ ChemA – Trợ lý Hóa học THPT")

if not st.session_state.messages:
    st.markdown(
        f"""
        <div class="hero-card">
            <ul>
                <li>📚 Giải thích lý thuyết, công thức, phản ứng.</li>
                <li>✍️ Hướng dẫn giải bài tập và chấm bài từ ảnh.</li>
                <li>⚗️ Cân bằng phương trình, tính toán hóa học.</li>
                <li>🧠 Ôn tập, làm quiz, phân tích điểm yếu.</li>
            </ul>
            <hr>
            <p>🎯 Sẵn sàng chưa? Hãy gõ câu hỏi hoặc tải ảnh đề bài lên nhé! 📸</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

# Hiển thị lịch sử chat
for msg in st.session_state.messages:
    avatar_icon = "⚛️" if msg["role"] == "assistant" else "🧑‍🎓"
    with st.chat_message(msg["role"], avatar=avatar_icon):
        if msg.get("image_display_bytes"):
             try:
                 img_stream = io.BytesIO(msg["image_display_bytes"])
                 st.image(img_stream, caption="Ảnh bạn đã tải", use_container_width=True)
             except Exception as e:
                 st.caption(f"[Không thể hiển thị lại ảnh: {e}]")

        if msg.get("content"):
            st.markdown(msg["content"], unsafe_allow_html=True)
        if msg.get("footnote"):
            st.caption(msg["footnote"])

# Hàm lưu trữ tạm thời ở phiên làm việc hiện tại
def _store_turn(question: str, answer: str, metadata: dict, footnote: Optional[str] = None, image_name: Optional[str] = None) -> None:
    timestamp = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    turn_entry = {
        "timestamp": timestamp, "question": question, "answer": answer,
        "mode": st.session_state.current_mode,
    }
    if image_name: turn_entry["image_name"] = image_name
    if metadata: turn_entry["metadata"] = metadata
    if footnote: turn_entry["footnote"] = footnote
    st.session_state.turns.append(turn_entry)

# Khung nhập liệu Chat  
prompt = st.chat_input("Nhập câu hỏi, phương trình, hoặc tải ảnh lên và hỏi...")

if prompt:
    # 1. Hiển thị tin nhắn người dùng
    user_avatar = "🧑‍🎓"
    user_message_content = prompt
    pending_file_obj = st.session_state.uploaded_file_data

    user_message_to_display = {"role": "user", "content": user_message_content}
    image_bytes_for_display = None

    with st.chat_message("user", avatar=user_avatar):
        if pending_file_obj:
            try:
                image_bytes_for_display = pending_file_obj.getvalue()
                user_message_to_display["image_display_bytes"] = image_bytes_for_display
                st.image(image_bytes_for_display, caption="Ảnh đã tải", use_container_width=True)
            except Exception as e:
                st.error(f"Không thể đọc/hiển thị ảnh: {e}")
            st.markdown(user_message_content)
        else:
            st.markdown(user_message_content)

    st.session_state.messages.append(user_message_to_display)

    # Xử lý logic và nhận phản hồi từ Bot
    assistant_avatar = "⚛️"
    response_metadata = {}
    full_response_text = ""

    # Ưu tiên 1: Cân bằng phương trình (chỉ khi không có ảnh)
    if (("->" in prompt) or ("→" in prompt)) and not pending_file_obj:
        strategy = "balance"
        try:
            response_text = balance_equation(prompt.replace("→", "->"))
            full_response_text = response_text
            with st.chat_message("assistant", avatar=assistant_avatar):
                st.markdown(response_text)
                st.caption("⚖️ Đã cân bằng phương trình.")
                with st.expander("Gợi ý tính nhanh"):
                    st.markdown(hint_stoichiometry())

            assistant_message = {"role": "assistant", "content": response_text}
            st.session_state.messages.append(assistant_message)
            response_metadata = {"strategy": strategy}

        except Exception as e:
            strategy = "balance_error"
            error_message = f"Lỗi cân bằng phương trình: {e}. Vui lòng kiểm tra cú pháp."
            full_response_text = error_message
            with st.chat_message("assistant", avatar=assistant_avatar):
                st.error(error_message)
            assistant_message = {"role": "assistant", "content": error_message}
            st.session_state.messages.append(assistant_message)
            response_metadata = {"strategy": strategy, "error": str(e)}

    # Ưu tiên 2: Xử lý RAG hoặc Multimodal (Ảnh) bằng Streaming
    else:
        try:
            spinner_msg = f"ChemA ({st.session_state.current_mode.split('(')[0].strip()}) đang xử lý... 🤔"
            with st.spinner(spinner_msg):
                file_to_process = None
                if pending_file_obj:
                    file_to_process = io.BytesIO(pending_file_obj.getvalue())
                    file_to_process.name = pending_file_obj.name

                stream_generator = engine.answer_stream(
                    prompt,
                    uploaded_file=file_to_process,
                    mode=st.session_state.current_mode
                )

                with st.chat_message("assistant", avatar=assistant_avatar):
                    stream_output = st.write_stream(stream_generator)

                if isinstance(stream_output, StreamOutput):
                    full_response_text = stream_output.final_text
                    response_metadata = {
                        "strategy": stream_output.strategy,
                        "top_score": stream_output.top_score,
                        "sources": stream_output.sources
                    }
                elif isinstance(stream_output, str):
                     full_response_text = stream_output
                     response_metadata = {"strategy": "stream_text_only"}
                else:
                    full_response_text = "Stream kết thúc với kết quả không hợp lệ."
                    response_metadata = {"strategy": "stream_invalid_output"}
                    st.chat_message("assistant", avatar=assistant_avatar).error(full_response_text)

            if full_response_text and "error" not in response_metadata.get("strategy", ""):
                 assistant_message = {"role": "assistant", "content": full_response_text}
                 st.session_state.messages.append(assistant_message)

        except Exception as e:
            error_message = f"Đã xảy ra lỗi hệ thống nghiêm trọng: {e}"
            full_response_text = error_message
            with st.chat_message("assistant", avatar=assistant_avatar):
                st.error(error_message)
            print(f"Lỗi trong quá trình xử lý stream tại app.py: {e}")
            import traceback
            traceback.print_exc()
            assistant_message = {"role": "assistant", "content": error_message}
            st.session_state.messages.append(assistant_message)
            response_metadata = {"strategy": "app_error", "error": str(e)}

    #Lưu lại lượt chat vào lịch sử đầy đủ
    _store_turn(
        question=user_message_content,
        answer=full_response_text,
        metadata=response_metadata,
        image_name=pending_file_obj.name if pending_file_obj else None
    )

    #Dọn dẹp file trong state và rerun
    st.session_state.uploaded_file_data = None
    st.session_state.current_file_id = None
    st.rerun()