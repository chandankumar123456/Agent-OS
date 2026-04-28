"""MCP Document Server — provides document parsing, chunking, and summarization."""
# Stdout sanitization MUST be the first import to prevent any library from
# corrupting the JSON-RPC stdio transport.
import app.mcp.servers._stdio_sanitize  # noqa: F401, E402

import json
import os
import sys

os.environ["AGENTOS_LOG_STDERR"] = "1"

from typing import Optional
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("document")

from app.pipelines.document_ingestion import DocumentParser, TextChunker, DocumentSummarizer


def _fmt(tool_output) -> str:
    if tool_output.success:
        return json.dumps({"success": True, "result": tool_output.result})
    return json.dumps({"success": False, "error": tool_output.error})


@mcp.tool()
async def parse(path: str, skip_summary: bool = False) -> str:
    """Parse a document (PDF, DOCX, TXT, Markdown) and return extracted text, chunks, and summary.

    Args:
        path: Absolute path to the document.
        skip_summary: If True, skip LLM summarization.
    """
    if not path or not os.path.exists(path):
        return json.dumps({"success": False, "error": f"File not found: {path}"})
    try:
        from app.pipelines.document_ingestion import DocumentIngestionPipeline
        pipeline = DocumentIngestionPipeline()
        doc = await pipeline.process(path, skip_summary=skip_summary)
        return json.dumps({
            "success": True,
            "result": {
                "path": path,
                "text": doc.text,
                "summary": doc.summary,
                "chunks": doc.chunks,
                "metadata": doc.metadata,
            },
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@mcp.tool()
async def parse_pdf(path: str) -> str:
    """Parse a PDF file and return extracted text and metadata."""
    if not path or not os.path.exists(path):
        return json.dumps({"success": False, "error": f"File not found: {path}"})
    try:
        doc = DocumentParser.parse_pdf(path)
        return json.dumps({
            "success": True,
            "result": {
                "path": path,
                "text": doc.text,
                "metadata": doc.metadata,
            },
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@mcp.tool()
async def parse_docx(path: str) -> str:
    """Parse a DOCX file and return extracted text and metadata."""
    if not path or not os.path.exists(path):
        return json.dumps({"success": False, "error": f"File not found: {path}"})
    try:
        doc = DocumentParser.parse_docx(path)
        return json.dumps({
            "success": True,
            "result": {
                "path": path,
                "text": doc.text,
                "metadata": doc.metadata,
            },
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@mcp.tool()
async def parse_txt(path: str) -> str:
    """Parse a plain text file and return its contents."""
    if not path or not os.path.exists(path):
        return json.dumps({"success": False, "error": f"File not found: {path}"})
    try:
        doc = DocumentParser.parse_txt(path)
        return json.dumps({
            "success": True,
            "result": {
                "path": path,
                "text": doc.text,
                "metadata": doc.metadata,
            },
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@mcp.tool()
async def parse_markdown(path: str) -> str:
    """Parse a Markdown file and return cleaned text."""
    if not path or not os.path.exists(path):
        return json.dumps({"success": False, "error": f"File not found: {path}"})
    try:
        doc = DocumentParser.parse_markdown(path)
        return json.dumps({
            "success": True,
            "result": {
                "path": path,
                "text": doc.text,
                "metadata": doc.metadata,
            },
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@mcp.tool()
async def chunk(text: str, chunk_size: int = 2000, overlap: int = 200) -> str:
    """Split text into semantic chunks.

    Args:
        text: The text to chunk.
        chunk_size: Maximum characters per chunk.
        overlap: Overlap between chunks in characters.
    """
    try:
        chunker = TextChunker(chunk_size=chunk_size, overlap=overlap)
        chunks = chunker.chunk(text)
        return json.dumps({"success": True, "result": {"chunks": chunks}})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@mcp.tool()
async def summarize(path: str) -> str:
    """Summarize a document using LLM.

    Args:
        path: Absolute path to the document.
    """
    if not path or not os.path.exists(path):
        return json.dumps({"success": False, "error": f"File not found: {path}"})
    try:
        from app.pipelines.document_ingestion import DocumentIngestionPipeline
        pipeline = DocumentIngestionPipeline()
        doc = await pipeline.process(path, skip_summary=False)
        return json.dumps({
            "success": True,
            "result": {
                "path": path,
                "summary": doc.summary,
                "text_preview": doc.text[:1000],
            },
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


if __name__ == "__main__":
    # Eagerly import the LLM client chain before anyio starts the event loop.
    # On Windows, importing pyautogui (pulled in via app.agents.planner →
    # app.tools.registry → app.environments.desktop_env) hangs indefinitely
    # when done inside the active anyio stdio transport task group.
    # Pre-importing here forces the heavy imports to complete before the loop.
    import app.agents.llm_client  # noqa: F401
    mcp.run(transport="stdio")
