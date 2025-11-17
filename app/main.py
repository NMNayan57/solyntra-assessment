from fastapi import FastAPI, UploadFile, File, HTTPException
from typing import List
import logging

from app.rag import RAGSystem
from app.utils import extract_text_from_file

# Basic logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Solyntra AI Knowledge Assistant")

# Single RAG system instance for the app
rag_system = RAGSystem()


@app.post("/upload")
async def upload_documents(files: List[UploadFile] = File(...)):
    """
    Upload 1–3 PDF/TXT files, extract text, chunk, embed and store in vector DB.
    """
    try:
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")

        if len(files) > 3:
            raise HTTPException(status_code=400, detail="Maximum 3 files allowed")

        logger.info(f"Received {len(files)} file(s) for upload")

        results = []

        for file in files:
            # Extract text from uploaded file
            text = await extract_text_from_file(file)

            if not text or len(text.strip()) == 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"No readable text found in file: {file.filename}",
                )

            # Add document to RAG system (chunk + embed + store)
            doc_id = rag_system.add_document(text, source=file.filename)

            results.append(
                {
                    "filename": file.filename,
                    "doc_id": doc_id,
                    "status": "processed",
                }
            )

            logger.info(f"Processed file: {file.filename}, doc_id={doc_id}")

        return {
            "message": "Documents uploaded and indexed successfully",
            "documents": results,
        }

    except HTTPException:
        # Re-raise HTTP exceptions as is
        raise
    except Exception:
        logger.exception("Error during upload")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/ask")
async def ask_question(query: str):
    """
    Answer a question using RAG over uploaded documents.
    """
    try:
        if not query or len(query.strip()) == 0:
            raise HTTPException(status_code=400, detail="Query cannot be empty")

        logger.info(f"Received query: {query}")

        result = rag_system.answer_query(query)

        return result

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error during question answering")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/health")
async def health_check():
    """
    Simple health check endpoint.
    """
    return {
        "status": "ok",
        "indexed_chunks": rag_system.get_vector_count(),
    }


@app.get("/metrics")
async def metrics():
    """
    Simple in-memory metrics for uploads and queries.
    """
    avg_latency = (
        rag_system.total_query_time / rag_system.total_queries
        if rag_system.total_queries > 0
        else 0.0
    )

    return {
        "total_uploads": rag_system.total_uploads,
        "total_queries": rag_system.total_queries,
        "avg_query_latency_seconds": round(avg_latency, 3),
        "indexed_chunks": rag_system.get_vector_count(),
    }
