import os
import streamlit as st
from dotenv import load_dotenv

# Chỉ load .env khi chạy local
load_dotenv()

def get_secret(key: str, default=None):
    """Ưu tiên lấy từ st.secrets, fallback sang os.getenv"""
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)

# API keys
GEMINI_API_KEY = get_secret("GOOGLE_API_KEY")
GEMINI_MODEL = get_secret("GEMINI_MODEL", "gemini-2.5-pro")
EMBED_MODEL = get_secret("EMBED_MODEL", "text-embedding-004")

# Retrieval
TOP_K = int(get_secret("TOP_K", 4))
CHUNK_SIZE = int(get_secret("CHUNK_SIZE", 900))
CHUNK_OVERLAP = int(get_secret("CHUNK_OVERLAP", 200))
MIN_SIMILARITY = float(get_secret("MIN_SIMILARITY", 0.32))

# Persistence
MONGO_URI = get_secret("MONGO_URI", "")
MONGO_DB = get_secret("MONGO_DB", "chema")
MONGO_COLLECTION = get_secret("MONGO_COLLECTION", "conversations")
