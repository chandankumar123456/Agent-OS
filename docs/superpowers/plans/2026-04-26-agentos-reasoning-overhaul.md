# AgentOS Reasoning & Tool Grounding Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:dispatching-parallel-agents for independent modules, then superpowers:subagent-driven-development for integration.

**Goal:** Fix AgentOS tool hallucination, incorrect tool selection, missing tool handling, and weak workflow decomposition. Make complex multi-step tasks deterministic and verifiable.

**Architecture:** New deterministic layers (ToolGrounding, WorkflowDecomposer, DocumentIngestion, DynamicToolBuilder) sit between intent and execution. LLM is only used for summarization and ambiguous reasoning. Tool selection, environment routing, and phase transitions are deterministic.

**Tech Stack:** Python 3.11, FastAPI, LangGraph, Redis, PostgreSQL, Playwright

---

## File Ownership Map

| File | Purpose |
|------|---------|
| `app/tools/grounding.py` | **NEW**: Capability→tool registry mapping. Filters tools per phase. |
| `app/workflows/decomposer.py` | **NEW**: Breaks complex tasks into structured phases with tool registries. |
| `app/pipelines/document_ingestion.py` | **NEW**: PDF/DOCX/TXT/Markdown extraction, cleaning, chunking, summarization. |
| `app/tools/builder.py` | **NEW**: DynamicToolFactory — builds missing tools on-the-fly via code gen + registration. |
| `app/capabilities/verification.py` | **MODIFY**: Add browser_opened, html_rendered, file_created verifiers. |
| `app/langgraph/nodes.py` | **MODIFY**: Integrate grounding layer, decomposer, deterministic tool selection. |
| `app/tools/registry.py` | **MODIFY**: Add `get_by_prefix`, `get_by_capability`, builder hooks. |
| `app/capabilities/router.py` | **MODIFY**: Expand `_suggest_tools` with grounded tool sets. |

---

## Subsystem 1: Tool Grounding Layer

**Goal:** Planner/executor can NEVER select tools outside the allowed set for a given intent.

### Task 1.1: Create `app/tools/grounding.py`

**Files:**
- Create: `app/tools/grounding.py`
- Modify: `app/tools/__init__.py`

```python
"""Tool Grounding Layer — deterministic capability-to-tool mapping."""
from typing import Dict, List, Set, Optional, Any
from enum import Enum

class ToolCategory(str, Enum):
    FILESYSTEM = "filesystem"
    BROWSER = "browser"
    DESKTOP = "desktop"
    SHELL = "shell"
    CLOUD = "cloud"
    CODE = "code"
    DOCUMENT = "document"
    COMMUNICATION = "communication"
    SEARCH = "search"
    CALCULATION = "calculation"
    UNKNOWN = "unknown"


# Capability → allowed tool name patterns
CAPABILITY_TOOL_MAP: Dict[str, List[str]] = {
    "file_search": [
        "filesystem__search_files",
        "filesystem__list_directory",
        "shell__execute_command",
        "desktop__desktop__get_window_list",
        "desktop_env__get_window_list",
    ],
    "file_read": [
        "filesystem__read_file",
        "shell__execute_command",
    ],
    "file_write": [
        "filesystem__write_file",
        "shell__execute_command",
    ],
    "document_processing": [
        "document__parse_pdf",
        "document__parse_docx",
        "document__parse_txt",
        "document__parse_markdown",
        "filesystem__read_file",
        "text_processor",
    ],
    "browser_navigation": [
        "browser_env__launch",
        "browser_env__navigate",
        "browser_env__search",
        "browser_env__click",
        "browser_env__type",
        "browser_env__screenshot",
        "browser_env__get_text",
        "browser_env__close",
    ],
    "web_search": [
        "cloud_api__search_web",
        "cloud_api__http_request",
        "cloud_api__scrape_page",
        "web_search",
    ],
    "shell_execution": [
        "shell__execute_command",
        "shell__run_script",
        "shell__get_process_status",
    ],
    "desktop_automation": [
        "desktop_env__screenshot",
        "desktop_env__click",
        "desktop_env__type_text",
        "desktop_env__press_key",
        "desktop_env__get_window_list",
        "desktop_env__focus_window",
        "desktop_env__get_clipboard",
        "desktop_env__set_clipboard",
        "desktop_env__scroll",
        "desktop__desktop__screenshot",
        "desktop__desktop__click",
        "desktop__desktop__type_text",
        "desktop__desktop__press_key",
        "desktop__desktop__get_window_list",
        "desktop__desktop__focus_window",
    ],
    "communication": [
        "cloud_api__send_email",
        "cloud_api__send_message",
        "slack__send_message",
    ],
    "code_execution": [
        "code_executor__run_python",
        "shell__execute_command",
        "shell__run_script",
    ],
    "calculation": [
        "calculator",
    ],
    "general": [
        "text_processor",
        "web_search",
        "calculator",
    ],
}

# Step intent keywords → capability
STEP_INTENT_MAP: Dict[str, str] = {
    # File operations
    "find file": "file_search",
    "search file": "file_search",
    "locate file": "file_search",
    "list directory": "file_search",
    "open folder": "file_search",
    "open file explorer": "desktop_automation",  # On Windows, opening Explorer is desktop
    "read file": "file_read",
    "extract text": "document_processing",
    "parse pdf": "document_processing",
    "parse docx": "document_processing",
    "summarize document": "document_processing",
    # Browser
    "open chrome": "browser_navigation",
    "open browser": "browser_navigation",
    "navigate to": "browser_navigation",
    "search in browser": "browser_navigation",
    "browse": "browser_navigation",
    # Desktop
    "click": "desktop_automation",
    "screenshot": "desktop_automation",
    "type text": "desktop_automation",
    "press key": "desktop_automation",
    "focus window": "desktop_automation",
    # Shell
    "run command": "shell_execution",
    "execute command": "shell_execution",
    "open in chrome": "shell_execution",  # Opening local HTML in Chrome uses shell
    # Web
    "search web": "web_search",
    "fetch data": "web_search",
    "scrape": "web_search",
    # Code
    "run python": "code_execution",
    "execute code": "code_execution",
    # Write
    "create file": "file_write",
    "write file": "file_write",
    "generate html": "file_write",
    "generate css": "file_write",
    "generate js": "file_write",
}


class ToolGroundingLayer:
    """Deterministically maps task intent to allowed tool sets."""

    def classify_intent(self, step_description: str) -> str:
        """Classify a step description into a capability intent."""
        desc_lower = step_description.lower()
        best_intent = "general"
        best_score = 0
        for keyword, intent in STEP_INTENT_MAP.items():
            if keyword in desc_lower:
                # Prefer longer/more specific matches
                score = len(keyword)
                if score > best_score:
                    best_score = score
                    best_intent = intent
        return best_intent

    def get_allowed_tools(self, intent: str, all_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter the full tool list to only tools allowed for this intent."""
        allowed_patterns = CAPABILITY_TOOL_MAP.get(intent, CAPABILITY_TOOL_MAP["general"])
        allowed = []
        for tool in all_tools:
            name = tool.get("name", "")
            # Exact match or prefix match
            for pattern in allowed_patterns:
                if name == pattern or name.startswith(pattern.replace("__", "__").rsplit("__", 1)[0] + "__"):
                    allowed.append(tool)
                    break
        # If no tools matched, fall back to general but warn
        if not allowed:
            # Try broader match: include all tools that aren't clearly wrong
            forbidden_prefixes = self._get_forbidden_prefixes(intent)
            allowed = [t for t in all_tools if not any(t.get("name", "").startswith(fp) for fp in forbidden_prefixes)]
        return allowed

    def _get_forbidden_prefixes(self, intent: str) -> Set[str]:
        """Return tool prefixes that should NEVER be used for a given intent."""
        # Map of intent → clearly wrong tool categories
        forbidden_map = {
            "file_search": {"browser_env__", "cloud_api__send"},
            "browser_navigation": {"desktop_env__", "shell__execute_command"},
            "desktop_automation": {"browser_env__", "cloud_api__"},
            "shell_execution": {"browser_env__", "cloud_api__send", "desktop_env__"},
        }
        return forbidden_map.get(intent, set())

    def filter_tools_for_step(self, step_description: str, all_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Main entry point: given a step description, return grounded tools."""
        intent = self.classify_intent(step_description)
        return self.get_allowed_tools(intent, all_tools)

    def get_intent_for_tool(self, tool_name: str) -> Optional[str]:
        """Reverse lookup: what intent is a tool valid for?"""
        for intent, patterns in CAPABILITY_TOOL_MAP.items():
            for pattern in patterns:
                if tool_name == pattern or tool_name.startswith(pattern.rsplit("__", 1)[0] + "__"):
                    return intent
        return None

    def is_tool_allowed(self, tool_name: str, step_description: str) -> bool:
        """Check if a specific tool is allowed for a step."""
        intent = self.classify_intent(step_description)
        allowed = self.get_allowed_tools(intent, [{"name": tool_name}])
        return len(allowed) > 0


# Singleton
tool_grounding_layer = ToolGroundingLayer()
```

---

## Subsystem 2: Workflow Decomposition Engine

**Goal:** Complex tasks are decomposed into structured phases, each with its own tool registry and verification criteria.

### Task 2.1: Create `app/workflows/decomposer.py`

**Files:**
- Create: `app/workflows/decomposer.py`
- Create: `app/workflows/__init__.py`

```python
"""Workflow Decomposition Engine — breaks complex tasks into structured phases."""
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

from ..logs.logger import logger


@dataclass
class WorkflowPhase:
    """A single phase in a decomposed workflow."""
    phase_id: str
    name: str
    description: str
    intent: str  # From ToolGroundingLayer
    verification_criteria: List[Dict[str, Any]] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)


class WorkflowDecomposer:
    """Decomposes complex user queries into executable phases.

    Instead of one giant plan, produces phases like:
    - file_search → file_read → document_process → file_write → browser_open
    """

    # Phase detection patterns
    PHASE_PATTERNS: List[Dict[str, Any]] = [
        {
            "name": "file_search",
            "intents": ["find", "search", "locate", "look for", "where is"],
            "tools_hint": ["filesystem__search_files", "filesystem__list_directory", "desktop_env__get_window_list"],
            "verification": [{"type": "file_found", "path_extractor": True}],
        },
        {
            "name": "file_read",
            "intents": ["read", "open file", "extract content", "get text from"],
            "tools_hint": ["filesystem__read_file"],
            "verification": [{"type": "file_exists"}, {"type": "content_extracted"}],
        },
        {
            "name": "document_processing",
            "intents": ["summarize", "parse pdf", "parse docx", "extract from document", "chunk"],
            "tools_hint": ["document__parse_pdf", "document__parse_docx", "text_processor"],
            "verification": [{"type": "content_extracted"}, {"type": "summary_generated"}],
        },
        {
            "name": "content_generation",
            "intents": ["create html", "create css", "create js", "generate html", "generate css", "generate js", "write file", "create file"],
            "tools_hint": ["filesystem__write_file", "shell__execute_command"],
            "verification": [{"type": "file_exists"}, {"type": "file_contains", "pattern": "html|css|javascript"}],
        },
        {
            "name": "browser_open",
            "intents": ["open in chrome", "open in browser", "view in browser", "show in chrome"],
            "tools_hint": ["shell__execute_command", "browser_env__navigate"],
            "verification": [{"type": "browser_opened", "url_extractor": True}],
        },
        {
            "name": "browser_navigation",
            "intents": ["browse", "navigate", "search in browser", "open website", "login to"],
            "tools_hint": ["browser_env__launch", "browser_env__navigate", "browser_env__search"],
            "verification": [{"type": "browser_navigated"}],
        },
        {
            "name": "desktop_automation",
            "intents": ["click", "type", "screenshot", "focus window", "open app"],
            "tools_hint": ["desktop_env__click", "desktop_env__type_text", "desktop_env__screenshot", "desktop_env__focus_window"],
            "verification": [{"type": "desktop_action_completed"}],
        },
        {
            "name": "shell_execution",
            "intents": ["run command", "execute command", "install", "git ", "docker ", "npm ", "pip "],
            "tools_hint": ["shell__execute_command", "shell__run_script"],
            "verification": [{"type": "command_succeeds"}],
        },
        {
            "name": "web_search",
            "intents": ["search web", "find online", "google", "look up"],
            "tools_hint": ["cloud_api__search_web", "cloud_api__http_request", "web_search"],
            "verification": [{"type": "web_content"}],
        },
    ]

    def decompose(self, query: str) -> List[WorkflowPhase]:
        """Decompose a user query into ordered workflow phases."""
        query_lower = query.lower()
        phases: List[WorkflowPhase] = []
        matched_intents: set = set()

        for pattern in self.PHASE_PATTERNS:
            for intent_keyword in pattern["intents"]:
                if intent_keyword in query_lower:
                    if pattern["name"] in matched_intents:
                        break
                    matched_intents.add(pattern["name"])
                    phases.append(WorkflowPhase(
                        phase_id=f"phase_{len(phases) + 1}",
                        name=pattern["name"],
                        description=f"Execute {pattern['name']} phase",
                        intent=pattern["name"],
                        verification_criteria=pattern.get("verification", []),
                    ))
                    break

        # If no phases detected, fall back to a single generic phase
        if not phases:
            phases.append(WorkflowPhase(
                phase_id="phase_1",
                name="general_execution",
                description="Execute the user request",
                intent="general",
            ))

        # Add dependencies
        for i, phase in enumerate(phases):
            if i > 0:
                phase.depends_on = [phases[i - 1].phase_id]

        logger.info(f"[WorkflowDecomposer] Decomposed query into {len(phases)} phases: {[p.name for p in phases]}")
        return phases

    def extract_paths(self, text: str) -> List[str]:
        """Extract likely file paths from text."""
        # Windows and Unix absolute paths
        pattern = re.compile(r"([A-Za-z]:\\[^\s\"'<>]+|/~?(?:/[^\s\"'<>]+)+|(?:\$HOME|~)/[^\s\"'<>]+)")
        return pattern.findall(text)

    def extract_urls(self, text: str) -> List[str]:
        """Extract URLs from text."""
        pattern = re.compile(r"https?://[^\s\"'<>]+")
        return pattern.findall(text)


# Singleton
workflow_decomposer = WorkflowDecomposer()
```

---

## Subsystem 3: Document Ingestion Pipeline

**Goal:** Support PDF, DOCX, TXT, Markdown with extract → clean → chunk → summarize.

### Task 3.1: Create `app/pipelines/document_ingestion.py`

**Files:**
- Create: `app/pipelines/document_ingestion.py`
- Create: `app/pipelines/__init__.py`
- Modify: `app/tools/registry.py` (register document tools)

```python
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
        # Strip markdown syntax for plain text extraction
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
            doc = docx.Document(path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
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
            # Try to break at paragraph
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
        # 1. Extract
        doc = self.parser.parse(path)
        if not doc.text:
            logger.warning(f"[DocumentIngestion] No text extracted from {path}")
            return doc
        # 2. Clean
        doc.text = self._clean_text(doc.text)
        # 3. Chunk
        doc.chunks = self.chunker.chunk(doc.text)
        # 4. Summarize
        if not skip_summary:
            doc.summary = await self.summarizer.summarize(doc)
        logger.info(f"[DocumentIngestion] Completed {path}: {len(doc.text)} chars, {len(doc.chunks)} chunks")
        return doc

    def _clean_text(self, text: str) -> str:
        # Remove excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n[ \t]+", "\n", text)
        # Remove control chars except newlines
        text = "".join(ch for ch in text if ch == "\n" or (ord(ch) >= 32 and ord(ch) < 127) or ord(ch) > 127)
        return text.strip()


# Document tools for registry
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
```

---

## Subsystem 4: Dynamic Tool Builder

**Goal:** If a needed tool doesn't exist, build it automatically instead of failing.

### Task 4.1: Create `app/tools/builder.py`

**Files:**
- Create: `app/tools/builder.py`

```python
"""Dynamic Tool Builder — builds missing tools on-the-fly."""
import asyncio
import inspect
from typing import Dict, Any, Optional, Callable
from ..tools.base import BaseTool, ToolInput, ToolOutput
from ..logs.logger import logger


class DynamicToolFactory:
    """Creates tools dynamically when they are missing.

    Strategies:
    1. Compose from existing MCP tools (e.g., search + read = find_and_read)
    2. Generate Python wrapper code for common patterns
    3. Register the new tool immediately
    """

    def __init__(self, registry):
        self.registry = registry
        self._built_tools: set = set()

    async def ensure_tool(self, tool_name: str) -> bool:
        """Check if tool exists; if not, try to build it. Returns True if available."""
        if self.registry.get(tool_name):
            return True
        if tool_name in self._built_tools:
            return self.registry.get(tool_name) is not None

        logger.info(f"[DynamicToolFactory] Tool '{tool_name}' missing. Attempting to build...")
        built = await self._build_tool(tool_name)
        if built:
            self._built_tools.add(tool_name)
        return built

    async def _build_tool(self, tool_name: str) -> bool:
        """Attempt to construct a missing tool."""
        # Strategy 1: filesystem tools via shell fallback
        if tool_name.startswith("filesystem__"):
            return await self._build_filesystem_tool(tool_name)
        # Strategy 2: document parser tools
        if tool_name.startswith("document__"):
            return await self._build_document_tool(tool_name)
        # Strategy 3: browser convenience tools
        if tool_name.startswith("browser__"):
            return await self._build_browser_tool(tool_name)
        # Strategy 4: shell wrappers
        if tool_name.startswith("shell__"):
            return await self._build_shell_tool(tool_name)
        return False

    async def _build_filesystem_tool(self, tool_name: str) -> bool:
        """Build filesystem tools using shell fallback or direct Python."""
        from ..tools.registry import MCPWrappedTool
        # Check if MCP filesystem server is available
        if self.registry.get("shell__execute_command"):
            # Create a wrapper that delegates to shell
            if tool_name == "filesystem__search_files":
                return self._register_from_callable(
                    tool_name,
                    self._search_files_impl,
                    "Search for files matching a pattern using shell find/dir commands.",
                    {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "pattern": {"type": "string"},
                        },
                        "required": ["path", "pattern"],
                    },
                )
            if tool_name == "filesystem__list_directory":
                return self._register_from_callable(
                    tool_name,
                    self._list_directory_impl,
                    "List directory contents.",
                    {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                )
            if tool_name == "filesystem__read_file":
                return self._register_from_callable(
                    tool_name,
                    self._read_file_impl,
                    "Read file contents.",
                    {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                )
            if tool_name == "filesystem__write_file":
                return self._register_from_callable(
                    tool_name,
                    self._write_file_impl,
                    "Write content to a file.",
                    {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["path", "content"],
                    },
                )
        return False

    def _register_from_callable(
        self, name: str, fn: Callable, description: str, schema: Dict[str, Any]
    ) -> bool:
        """Wrap a Python function as a BaseTool and register it."""
        class DynamicTool(BaseTool):
            tool_name = name
            tool_description = description
            tool_schema = schema

            @property
            def name(self):
                return self.tool_name

            @property
            def description(self):
                return self.tool_description

            def get_schema(self):
                return {
                    "name": self.name,
                    "description": self.description,
                    "parameters": self.tool_schema,
                }

            async def execute(self, tool_input: ToolInput) -> ToolOutput:
                try:
                    if asyncio.iscoroutinefunction(fn):
                        result = await fn(**tool_input.parameters)
                    else:
                        result = fn(**tool_input.parameters)
                    if isinstance(result, ToolOutput):
                        return result
                    return ToolOutput(success=True, result={"output": result})
                except Exception as e:
                    return ToolOutput(success=False, error=str(e))

        self.registry.register(DynamicTool())
        logger.info(f"[DynamicToolFactory] Registered dynamic tool: {name}")
        return True

    @staticmethod
    async def _search_files_impl(path: str, pattern: str) -> ToolOutput:
        import os
        import fnmatch
        matches = []
        for root, dirs, files in os.walk(path):
            for name in files:
                if fnmatch.fnmatch(name.lower(), pattern.lower()) or pattern.lower() in name.lower():
                    matches.append(os.path.join(root, name))
            # Limit depth and results
            if len(matches) >= 100:
                break
        return ToolOutput(success=True, result={"matches": matches, "count": len(matches)})

    @staticmethod
    def _list_directory_impl(path: str) -> ToolOutput:
        import os
        if not os.path.isdir(path):
            return ToolOutput(success=False, error=f"Not a directory: {path}")
        entries = os.listdir(path)
        files = [e for e in entries if os.path.isfile(os.path.join(path, e))]
        dirs = [e for e in entries if os.path.isdir(os.path.join(path, e))]
        return ToolOutput(success=True, result={"path": path, "files": files, "directories": dirs})

    @staticmethod
    def _read_file_impl(path: str) -> ToolOutput:
        import os
        if not os.path.exists(path):
            return ToolOutput(success=False, error=f"File not found: {path}")
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return ToolOutput(success=True, result={"path": path, "content": content, "size": len(content)})
        except Exception as e:
            return ToolOutput(success=False, error=str(e))

    @staticmethod
    def _write_file_impl(path: str, content: str) -> ToolOutput:
        import os
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return ToolOutput(success=True, result={"path": path, "bytes_written": len(content.encode("utf-8"))})
        except Exception as e:
            return ToolOutput(success=False, error=str(e))

    async def _build_document_tool(self, tool_name: str) -> bool:
        if tool_name in ("document__parse_pdf", "document__parse_docx", "document__parse_txt", "document__parse_markdown"):
            # These are handled by the DocumentParseTool
            from ..pipelines.document_ingestion import DocumentParseTool
            self.registry.register(DocumentParseTool())
            return True
        return False

    async def _build_browser_tool(self, tool_name: str) -> bool:
        # Browser convenience tools map to existing browser_env tools
        return False  # Already have browser_env__*

    async def _build_shell_tool(self, tool_name: str) -> bool:
        if tool_name == "shell__execute_command":
            return self._register_from_callable(
                tool_name,
                self._shell_execute_impl,
                "Execute a shell command and return output.",
                {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "timeout": {"type": "integer", "default": 60},
                    },
                    "required": ["command"],
                },
            )
        return False

    @staticmethod
    async def _shell_execute_impl(command: str, timeout: int = 60) -> ToolOutput:
        import asyncio
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return ToolOutput(
                success=proc.returncode == 0,
                result={
                    "stdout": stdout.decode("utf-8", errors="ignore"),
                    "stderr": stderr.decode("utf-8", errors="ignore"),
                    "returncode": proc.returncode,
                },
            )
        except asyncio.TimeoutError:
            proc.kill()
            return ToolOutput(success=False, error=f"Command timed out after {timeout}s")


# Singleton instantiated after registry
dynamic_tool_factory: Optional[DynamicToolFactory] = None

def init_dynamic_tool_factory(registry):
    global dynamic_tool_factory
    dynamic_tool_factory = DynamicToolFactory(registry)
```

---

## Subsystem 5: Integration into Nodes

**Goal:** Wire grounding, decomposition, and tool building into the existing LangGraph nodes.

### Task 5.1: Modify `app/langgraph/nodes.py`

**Files:**
- Modify: `app/langgraph/nodes.py`

Changes needed:
1. Import grounding layer, decomposer, dynamic tool factory
2. In `planner_node`: decompose query into phases first, then generate plan per phase
3. In `executor_node`: filter available_tools through grounding layer before LLM prompt
4. In `executor_node`: if tool not found, call `dynamic_tool_factory.ensure_tool()` before failing
5. Reduce LLM calls by using deterministic tool selection when intent is clear

### Task 5.2: Modify `app/tools/registry.py`

Add `get_by_prefix` and builder hook in `get()`:
```python
def get(self, name: str) -> Optional[BaseTool]:
    registered = self.tools.get(name)
    if registered:
        return registered.tool
    # Try dynamic build
    from .builder import dynamic_tool_factory
    if dynamic_tool_factory:
        asyncio.create_task(dynamic_tool_factory.ensure_tool(name))
        # Re-check after build attempt
        registered = self.tools.get(name)
        return registered.tool if registered else None
    return None
```

### Task 5.3: Modify `app/capabilities/verification.py`

Add verifiers:
- `browser_opened` — check process list or HTTP ping
- `html_rendered` — verify HTML file has required tags
- `file_created` — already have file_exists
- `summary_generated` — check summary is non-empty

---

## Subsystem 6: LLM Call Reduction

**Goal:** Use deterministic logic instead of LLM for tool selection, retries, routing.

### Task 6.1: Deterministic Tool Selection in executor_node

Before calling LLM, check if step_description maps to a single obvious tool via grounding layer. If yes, execute directly without LLM.

### Task 6.2: Planner Cache

Use Redis to cache plans for identical queries (already in infrastructure plan).

---

## Verification

### Task E1: Unit tests for grounding
```python
def test_grounding_filters_browser_tools_for_file_search():
    all_tools = [{"name": "browser_env__launch"}, {"name": "filesystem__search_files"}]
    grounded = tool_grounding_layer.filter_tools_for_step("find my report", all_tools)
    assert any(t["name"] == "filesystem__search_files" for t in grounded)
    assert not any(t["name"].startswith("browser_env__") for t in grounded)
```

### Task E2: End-to-end test
Submit the exact failing query:
> "open file explorer, find my major project report, summarize it, create HTML/CSS/JS files, and open it in Chrome"

Verify:
1. Step 1 uses `desktop_env__get_window_list` or `shell__execute_command` (NOT `browser_env__launch`)
2. Step 2 uses `filesystem__search_files` or `shell__execute_command`
3. Step 3 uses `document__parse` or `filesystem__read_file`
4. Step 4 uses `filesystem__write_file`
5. Step 5 uses `shell__execute_command` to open Chrome
6. Files are created and verified
7. Browser opens and is verified

---

**Plan complete.**

**Execution choice:**
1. **Parallel Agents** — dispatch 4 agents concurrently for grounding, decomposer, ingestion, builder (recommended)
2. **Sequential Integration** — then integrate into nodes + registry + verification

**Recommendation:** Dispatch parallel agents for the 4 new modules, then integrate.
