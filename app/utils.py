from fastapi import UploadFile, HTTPException
import PyPDF2
import io
import logging
from docx import Document  # add this

logger = logging.getLogger(__name__)


async def extract_text_from_file(file: UploadFile) -> str:
    """
    Extract plain text from a PDF, TXT, or DOCX UploadFile.
    """
    try:
        content = await file.read()
        filename = file.filename.lower()

        # PDF files
        if filename.endswith(".pdf"):
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
            text_parts = []
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            text = "\n".join(text_parts)
            logger.info(f"Extracted {len(text)} characters from PDF: {file.filename}")
            return text

        # TXT files
        elif filename.endswith(".txt"):
            text = content.decode("utf-8", errors="ignore")
            logger.info(f"Extracted {len(text)} characters from TXT: {file.filename}")
            return text

        # DOCX files (new)
        elif filename.endswith(".docx"):
            doc = Document(io.BytesIO(content))
            text = "\n".join([para.text for para in doc.paragraphs])
            logger.info(f"Extracted {len(text)} characters from DOCX: {file.filename}")
            return text

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file.filename}. Use PDF, TXT, or DOCX.",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error extracting text from file: {file.filename}")
        raise HTTPException(status_code=500, detail="Failed to extract text from file")
