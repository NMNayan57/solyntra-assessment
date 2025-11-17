import os

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

EMBEDDING_MODEL = "text-embedding-3-small"
LLM_MODEL = "gpt-3.5-turbo"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
TOP_K = 5
VECTOR_DB = "faiss"
