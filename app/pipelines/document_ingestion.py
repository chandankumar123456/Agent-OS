"""Document Ingestion Pipeline — extract, clean, chunk, summarize."""
import os
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from ..logs.logger import logger
from ..tools.base import BaseTool, ToolInput, ToolOutput


@dataclass
class DocumentContent:
    source_path: str
    text: str
    metadata: Dict[str, Any]
    chunks: List[str]
    summary: Optional[str] = None


class DocumentParser:
    """Parse various document formats into clean text."""

    @staticmethod
    def parse_txt(path: str) -> DocumentContent:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        return DocumentContent(
            source_path=path,
            text=text,
            metadata={"format": "txt", "size": len(text)},
            chunks=[],
        )

    @staticmethod
    def parse_markdown(path: str) -> DocumentContent:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        clean = re.sub(r"[#*`\-\[\]\(\)|>!]", " ", text)
        clean = re.sub(r"\s+", " ", clean)
        return DocumentContent(
            source_path=path,
            text=clean.strip(),
            metadata={"format": "markdown", "size": len(text)},
            chunks=[],
        )

    @staticmethod
    def parse_pdf(path: str) -> DocumentContent:
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            return DocumentContent(
                source_path=path,
                text=text,
                metadata={"format": "pdf", "pages": len(pdf.pages), "size": len(text)},
                chunks=[],
            )
        except ImportError:
            logger.warning("pdfplumber not installed; falling back to basic read")
            return DocumentParser.parse_txt(path)
        except Exception as e:
            logger.error(f"PDF parse error: {e}")
            return DocumentContent(source_path=path, text="", metadata={"error": str(e)}, chunks=[])

    @staticmethod
    def parse_docx(path: str) -> DocumentContent:
        try:
            import docx
            document = docx.Document(path)
            paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
            text = "\n".join(paragraphs)
            return DocumentContent(
                source_path=path,
                text=text,
                metadata={"format": "docx", "paragraphs": len(paragraphs), "size": len(text)},
                chunks=[],
            )
        except ImportError:
            logger.warning("python-docx not installed; falling back to basic read")
            return DocumentParser.parse_txt(path)
        except Exception as e:
            logger.error(f"DOCX parse error: {e}")
            return DocumentContent(source_path=path, text="", metadata={"error": str(e)}, chunks=[])

    @classmethod
    def parse(cls, path: str) -> DocumentContent:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".pdf":
            return cls.parse_pdf(path)
        elif ext in (".docx", ".doc"):
            return cls.parse_docx(path)
        elif ext in (".md", ".markdown"):
            return cls.parse_markdown(path)
        else:
            return cls.parse_txt(path)


class TextChunker:
    """Split text into semantic chunks."""

    def __init__(self, chunk_size: int = 2000, overlap: int = 200):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str) -> List[str]:
        if len(text) <= self.chunk_size:
            return [text]
        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            if end < len(text):
                paragraph_break = text.rfind("\n\n", start, end)
                if paragraph_break > start + self.chunk_size // 2:
                    end = paragraph_break + 2
                else:
                    sentence_break = text.rfind(". ", start, end)
                    if sentence_break > start + self.chunk_size // 2:
                        end = sentence_break + 2
            chunks.append(text[start:end].strip())
            start = end - self.overlap
        return chunks


class DocumentSummarizer:
    """Summarize document content using LLM."""

    async def summarize(self, content: DocumentContent) -> str:
        from ..agents.llm_client import get_llm_client
        text = content.text
        if len(text) > 12000:
            text = text[:12000] + "\n... [truncated for summarization]"
        prompt = f"""Summarize the following document concisely. Capture the main points, key findings, and important details.

Document:
{text}

Provide a structured summary with:
- Main topic
- Key points (bullet points)
- Conclusions or recommendations"""
        try:
            response = await get_llm_client().complete_json(
                messages=[{"role": "user", "content": prompt}],
                response_schema={
                    "type": "object",
                    "properties": {"summary": {"type": "string"}},
                    "required": ["summary"],
                },
            )
            return response.get("summary", text[:1000])
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            return text[:2000] + "\n[Summarization failed, returning excerpt]"


class DocumentIngestionPipeline:
    """Full pipeline: locate → extract → clean → chunk → summarize."""

    def __init__(self):
        self.parser = DocumentParser()
        self.chunker = TextChunker()
        self.summarizer = DocumentSummarizer()

    async def process(self, path: str, skip_summary: bool = False) -> DocumentContent:
        logger.info(f"[DocumentIngestion] Processing {path}")
        doc = self.parser.parse(path)
        if not doc.text:
            logger.warning(f"[DocumentIngestion] No text extracted from {path}")
            return doc
        doc.text = self._clean_text(doc.text)
        doc.chunks = self.chunker.chunk(doc.text)
        if not skip_summary:
            doc.summary = await self.summarizer.summarize(doc)
        logger.info(f"[DocumentIngestion] Completed {path}: {len(doc.text)} chars, {len(doc.chunks)} chunks")
        return doc

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n[ \t]+", "\n", text)
        text = "".join(ch for ch in text if ch == "\n" or (ord(ch) >= 32 and ord(ch) < 127) or ord(ch) > 127)
        return text.strip()


class DocumentParseTool(BaseTool):
    name = "document__parse"
    description = "Parse a document (PDF, DOCX, TXT, Markdown) and return extracted text and summary."

    def get_schema(self):
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the document"},
                    "skip_summary": {"type": "boolean", "default": False},
                },
                "required": ["path"],
            },
        }

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        path = tool_input.parameters.get("path")
        skip_summary = tool_input.parameters.get("skip_summary", False)
        if not path or not os.path.exists(path):
            return ToolOutput(success=False, error=f"File not found: {path}")
        try:
            pipeline = DocumentIngestionPipeline()
            doc = await pipeline.process(path, skip_summary=skip_summary)
            return ToolOutput(
                success=True,
                result={
                    "path": path,
                    "text": doc.text,
                    "summary": doc.summary,
                    "chunks": doc.chunks,
                    "metadata": doc.metadata,
                },
                visibility={"type": "document_parsed", "path": path, "format": doc.metadata.get("format")},
            )
        except Exception as e:
            return ToolOutput(success=False, error=str(e))


# Singleton
pipeline = DocumentIngestionPipeline()
