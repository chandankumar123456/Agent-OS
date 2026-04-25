import io
from typing import List

from ..logs.logger import logger


def split_text_into_chunks(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    words = text.split()
    chunks: List[str] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


def parse_text(content: bytes, filename: str) -> str:
    return content.decode("utf-8", errors="ignore")


def parse_markdown(content: bytes, filename: str) -> str:
    return content.decode("utf-8", errors="ignore")


def parse_pdf(content: bytes, filename: str) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        logger.error(f"Failed to parse PDF {filename}: {e}")
        return content.decode("utf-8", errors="ignore")


def parse_document(content: bytes, filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return parse_pdf(content, filename)
    elif lower.endswith(".md"):
        return parse_markdown(content, filename)
    elif lower.endswith(".txt"):
        return parse_text(content, filename)
    else:
        return content.decode("utf-8", errors="ignore")
