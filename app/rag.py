from openai import OpenAI
import faiss
from functools import lru_cache
import logging
import time
import numpy as np

from app import config

logger = logging.getLogger(__name__)


class RAGSystem:
    """
    RAGSystem handles document ingestion, retrieval and answer generation.
    """

    def __init__(self):
        # Use OpenAI embeddings; text-embedding-3-small has 1536 dimensions
        self.embedding_dim = 1536

        # Initialize FAISS index (L2 distance)
        self.index = faiss.IndexFlatL2(self.embedding_dim)

        # Store chunks and metadata in Python lists
        self.chunks = []      # list of text chunks
        self.metadata = []    # list of dicts with source info

        # Simple in-memory metrics
        self.total_uploads = 0
        self.total_queries = 0
        self.total_query_time = 0.0  # seconds

        # OpenAI client (new SDK pattern)
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)
        self.llm_model = config.LLM_MODEL

        logger.info(
            f"RAGSystem initialized with OpenAI embeddings, dim={self.embedding_dim}"
        )

    def _chunk_text(self, text: str) -> list:
        """
        Split text into overlapping chunks.
        """
        words = text.split()
        chunks = []

        chunk_size = config.CHUNK_SIZE
        overlap = config.CHUNK_OVERLAP
        step = max(chunk_size - overlap, 1)

        for start in range(0, len(words), step):
            end = start + chunk_size
            chunk = " ".join(words[start:end])
            if chunk.strip():
                chunks.append(chunk)

        logger.info(f"Created {len(chunks)} chunk(s) from document")
        return chunks

    def _embed_texts(self, texts: list) -> np.ndarray:
        """
        Get embeddings for a list of texts using OpenAI embeddings API.
        """
        if not config.OPENAI_API_KEY:
            logger.error("OPENAI_API_KEY is not set")
            raise RuntimeError("OPENAI_API_KEY is not set")

        response = self.client.embeddings.create(
            model=config.EMBEDDING_MODEL,  # e.g. "text-embedding-3-small"
            input=texts,
        )

        embeddings = [item.embedding for item in response.data]
        return np.array(embeddings, dtype="float32")

    def add_document(self, text: str, source: str) -> int:
        """
        Add a document: chunk, embed and store in FAISS.
        Returns a document ID.
        """
        # Simple metric: count uploads
        self.total_uploads += 1

        chunks = self._chunk_text(text)

        # Generate embeddings for all chunks using OpenAI
        embeddings = self._embed_texts(chunks)

        # Add to FAISS index
        self.index.add(embeddings)

        # Store chunks and metadata
        doc_id = len({m.get("doc_id") for m in self.metadata})  # simple doc_id
        for i, chunk in enumerate(chunks):
            self.chunks.append(chunk)
            self.metadata.append(
                {
                    "doc_id": doc_id,
                    "chunk_id": i,
                    "source": source,
                }
            )

        logger.info(
            f"Document from source={source} added with {len(chunks)} chunk(s), doc_id={doc_id}"
        )
        return doc_id

    @lru_cache(maxsize=128)
    def _embed_query(self, query: str) -> np.ndarray:
        """
        Compute and cache query embedding using OpenAI embeddings.
        """
        embeddings = self._embed_texts([query])
        return embeddings[0]

    def _retrieve(self, query: str) -> list:
        """
        Retrieve top-k relevant chunks from FAISS for a given query.
        """
        if self.index.ntotal == 0:
            logger.warning("No documents indexed yet")
            return []

        query_vec = self._embed_query(query).reshape(1, -1)

        top_k = config.TOP_K
        distances, indices = self.index.search(query_vec, top_k)

        results = []
        for idx, dist in zip(indices[0], distances[0]):
            if 0 <= idx < len(self.chunks):
                results.append(
                    {
                        "text": self.chunks[idx],
                        "source": self.metadata[idx]["source"],
                        "distance": float(dist),
                    }
                )

        logger.info(f"Retrieved {len(results)} chunk(s) for query")
        return results

    def _build_context(self, retrieved_chunks: list) -> str:
        """
        Build context string from retrieved chunks.
        """
        parts = []
        for item in retrieved_chunks:
            parts.append(f"[Source: {item['source']}]\n{item['text']}")
        return "\n\n".join(parts)

    def _generate_answer(self, query: str, context: str) -> str:
        """
        Call LLM with query and context to generate answer.
        """
        if not config.OPENAI_API_KEY:
            logger.error("OPENAI_API_KEY is not set")
            return "LLM is not configured. Please set OPENAI_API_KEY."

        prompt = (
            "You are a helpful assistant. "
            "Use only the provided context to answer the question.\n\n"
            f"Context:\n{context}\n\n"
            f"Question: {query}\n\n"
            "Answer concisely:"
        )

        response = self.client.chat.completions.create(
            model=self.llm_model,
            messages=[
                {"role": "system", "content": "You answer based only on the given context."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=300,
        )

        answer = response.choices[0].message.content.strip()
        logger.info("Generated answer from LLM")
        return answer

    def answer_query(self, query: str) -> dict:
        """
        Full RAG pipeline: retrieve relevant chunks and generate answer.
        Also updates simple metrics (query count and latency).
        """
        start_time = time.time()
        self.total_queries += 1

        retrieved = self._retrieve(query)

        if not retrieved:
            duration = time.time() - start_time
            self.total_query_time += duration

            return {
                "answer": "No relevant information found in the uploaded documents.",
                "sources": [],
                "metrics": {
                    "latency_seconds": round(duration, 3),
                    "total_queries": self.total_queries,
                },
            }

        context = self._build_context(retrieved)
        answer = self._generate_answer(query, context)

        duration = time.time() - start_time
        self.total_query_time += duration

        avg_latency = (
            self.total_query_time / self.total_queries
            if self.total_queries > 0
            else 0.0
        )

        sources = [
            {
                "source": item["source"],
                "snippet": item["text"][:200] + ("..." if len(item["text"]) > 200 else ""),
            }
            for item in retrieved
        ]

        return {
            "answer": answer,
            "sources": sources,
            "metrics": {
                "latency_seconds": round(duration, 3),
                "avg_latency_seconds": round(avg_latency, 3),
                "total_queries": self.total_queries,
            },
        }

    def get_vector_count(self) -> int:
        """
        Return number of vectors stored in FAISS index.
        """
        return int(self.index.ntotal)
