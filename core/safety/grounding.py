"""Hallucination Grounding Layer for AgentOS.

Section 3.9: Prevents agents from generating outputs not grounded in
actual tool results or verified facts.

Architecture:
1. Fact Extraction — identifies factual claims in agent output
2. Source Verification — checks claims against tool results
3. Grounding Anchors — marks supported/unsupported claims
4. Grounding Score — overall reliability score (0.0 to 1.0)
5. Intervention — flags/rejects ungrounded outputs above threshold
"""
import json
import re
import hashlib
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from ..logs.logger import logger


# ─── Enums ────────────────────────────────────────────────────────────────
class GroundingStatus(str, Enum):
    """Status of a factual claim."""
    GROUNDED = "grounded"           # Verified by tool result
    UNSUPPORTED = "unsupported"      # No source found
    CONTRADICTED = "contradicted"    # Conflicts with tool result
    UNVERIFIABLE = "unverifiable"    # Cannot check (e.g., opinions)
    SUPPRESSED = "suppressed"        # Removed by grounding layer


class GroundingAction(str, Enum):
    """What to do with ungrounded content."""
    WARN = "warn"              # Log warning only
    ANNOTATE = "annotate"      # Mark unsupported claims
    REDACT = "redact"          # Remove unsupported claims
    REJECT = "reject"          # Reject entire output


# ─── Pydantic Models ──────────────────────────────────────────────────────
class FactClaim(BaseModel):
    """A single factual claim extracted from agent output."""
    claim_id: str = Field(default_factory=lambda: f"fc_{hashlib.sha256(str(datetime.now(timezone.utc)).encode()).hexdigest()[:10]}")
    claim_text: str
    claim_type: str = "fact"  # fact, statement, assertion, quote, number, path, url
    source_tool: Optional[str] = None
    source_result: Optional[Any] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    status: GroundingStatus = GroundingStatus.UNSUPPORTED
    anchor: Optional[str] = None  # Reference to grounding source
    verified_at: Optional[str] = None

    class Config:
        use_enum_values = True


class GroundingReport(BaseModel):
    """Result of grounding analysis on agent output."""
    report_id: str = Field(default_factory=lambda: f"gr_{hashlib.sha256(str(datetime.now(timezone.utc)).encode()).hexdigest()[:10]}")
    output_snippet: str = ""  # First 500 chars of output
    total_claims: int = 0
    grounded_claims: int = 0
    unsupported_claims: int = 0
    contradicted_claims: int = 0
    unverifiable_claims: int = 0
    grounding_score: float = 0.0  # 0.0 (fully hallucinated) to 1.0 (fully grounded)
    claims: List[FactClaim] = Field(default_factory=list)
    threshold_passed: bool = True
    action_taken: GroundingAction = GroundingAction.WARN
    recommendation: Optional[str] = None
    analyzed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    class Config:
        use_enum_values = True


class GroundingConfig(BaseModel):
    """Configuration for the grounding layer."""
    score_threshold: float = Field(default=0.5, ge=0.0, le=1.0, description="Minimum grounding score to pass")
    max_unsupported_ratio: float = Field(default=0.3, ge=0.0, le=1.0, description="Max ratio of unsupported claims allowed")
    action_on_failure: GroundingAction = Field(default=GroundingAction.WARN)
    check_paths: bool = True
    check_numbers: bool = True
    check_urls: bool = True
    check_assertions: bool = True
    min_confidence: float = Field(default=0.3, ge=0.0, le=1.0, description="Minimum confidence for a claim to be counted")

    class Config:
        use_enum_values = True


# ─── Fact Extractors ──────────────────────────────────────────────────────
class FactExtractor:
    """Extracts factual claims from agent output text."""

    # Patterns for identifying claims
    PATH_PATTERN = re.compile(
        r'(?:in|at|to|from|path[:\s]*|file[:\s]*|saved\s+(?:in|to|as)\s+)?'
        r'((?:[A-Za-z]:[\\/][^\s,.;"\'<>()]+)|(?:/(?:home|Users|usr|tmp|etc|var|opt)/[^\s,.;"\'<>()]+))',
        re.IGNORECASE,
    )
    URL_PATTERN = re.compile(r'(https?://[^\s,.;"\'<>()]+)', re.IGNORECASE)
    NUMBER_PATTERN = re.compile(r'\b(\d+(?:\.\d+)?\s*(?:MB|GB|TB|KB|%|ms|s|min|hours?|days?|files?|records?|items?|results?))\b', re.IGNORECASE)
    ASSERTION_PATTERN = re.compile(
        r'(?:The\s+)?(?:result\s+(?:is|was|shows?|indicates?|confirms?)|'
        r'(?:found|discovered|determined|verified|confirmed|identified)\s+that)\s+(.{10,200}?)(?:\.|$)',
        re.IGNORECASE,
    )

    @classmethod
    def extract(cls, text: str, config: GroundingConfig) -> List[FactClaim]:
        """Extract all factual claims from text."""
        claims: List[FactClaim] = []

        if config.check_paths:
            claims.extend(cls._extract_pattern_claims(text, cls.PATH_PATTERN, "path"))

        if config.check_urls:
            claims.extend(cls._extract_pattern_claims(text, cls.URL_PATTERN, "url"))

        if config.check_numbers:
            claims.extend(cls._extract_pattern_claims(text, cls.NUMBER_PATTERN, "number"))

        if config.check_assertions:
            claims.extend(cls._extract_assertion_claims(text))

        return claims

    @classmethod
    def _extract_pattern_claims(cls, text: str, pattern: re.Pattern, claim_type: str) -> List[FactClaim]:
        claims = []
        for match in pattern.finditer(text):
            claim_text = match.group(1).strip()
            claims.append(FactClaim(
                claim_text=claim_text,
                claim_type=claim_type,
                status=GroundingStatus.UNSUPPORTED,
            ))
        return claims

    @classmethod
    def _extract_assertion_claims(cls, text: str) -> List[FactClaim]:
        claims = []
        for match in cls.ASSERTION_PATTERN.finditer(text):
            claim_text = match.group(1).strip()
            if len(claim_text) >= 10:
                claims.append(FactClaim(
                    claim_text=claim_text,
                    claim_type="assertion",
                    status=GroundingStatus.UNSUPPORTED,
                ))
        return claims


# ─── Grounding Verifier ───────────────────────────────────────────────────
class GroundingVerifier:
    """Verifies factual claims against tool results and known facts."""

    @staticmethod
    def verify_path_claim(claim: FactClaim, tool_results: List[Dict[str, Any]]) -> FactClaim:
        """Verify a path claim against tool results."""
        claim_path = claim.claim_text.lower()
        for tool_result in tool_results:
            result_data = tool_result.get("data", {})
            result_error = tool_result.get("error")

            if result_error:
                continue

            # Check if result mentions this path
            result_str = json.dumps(result_data).lower() if result_data else ""
            if claim_path in result_str:
                claim.status = GroundingStatus.GROUNDED
                claim.source_tool = tool_result.get("tool", "unknown")
                claim.anchor = f"Tool result contains path: {claim_path[:50]}"
                claim.verified_at = datetime.now(timezone.utc).isoformat()
                return claim

            # Check for file operation results containing the path
            if isinstance(result_data, dict):
                for key in ("path", "file_path", "output_path", "created", "saved_to"):
                    val = result_data.get(key, "")
                    if isinstance(val, str) and claim_path in val.lower():
                        claim.status = GroundingStatus.GROUNDED
                        claim.source_tool = tool_result.get("tool", "unknown")
                        claim.anchor = f"Operation result confirms path at key '{key}'"
                        claim.verified_at = datetime.now(timezone.utc).isoformat()
                        return claim

        return claim  # Still UNSUPPORTED

    @staticmethod
    def verify_url_claim(claim: FactClaim, tool_results: List[Dict[str, Any]]) -> FactClaim:
        """Verify a URL claim against tool results."""
        claim_url = claim.claim_text.lower()
        for tool_result in tool_results:
            result_data = tool_result.get("data", {})
            result_str = json.dumps(result_data).lower() if result_data else ""

            if claim_url in result_str:
                claim.status = GroundingStatus.GROUNDED
                claim.source_tool = tool_result.get("tool", "unknown")
                claim.anchor = "Tool result references URL"
                claim.verified_at = datetime.now(timezone.utc).isoformat()
                return claim

            # Browser tool results
            if isinstance(result_data, dict):
                for key in ("url", "link", "href", "navigated_to"):
                    val = result_data.get(key, "")
                    if isinstance(val, str) and claim_url in val.lower():
                        claim.status = GroundingStatus.GROUNDED
                        claim.source_tool = tool_result.get("tool", "unknown")
                        claim.anchor = f"Browser result confirms URL at '{key}'"
                        claim.verified_at = datetime.now(timezone.utc).isoformat()
                        return claim

        return claim

    @staticmethod
    def verify_number_claim(claim: FactClaim, tool_results: List[Dict[str, Any]]) -> FactClaim:
        """Verify a numeric claim against tool results."""
        for tool_result in tool_results:
            result_data = tool_result.get("data", {})
            result_str = json.dumps(result_data) if result_data else ""
            if not result_str:
                continue

            # Extract the numeric part from claim
            num_match = re.search(r'(\d+(?:\.\d+)?)', claim.claim_text)
            if not num_match:
                continue
            claim_number = num_match.group(1)

            if claim_number in result_str:
                claim.status = GroundingStatus.GROUNDED
                claim.source_tool = tool_result.get("tool", "unknown")
                claim.anchor = f"Number {claim_number} found in tool result"
                claim.verified_at = datetime.now(timezone.utc).isoformat()
                return claim

        return claim

    @staticmethod
    def verify_assertion_claim(claim: FactClaim, tool_results: List[Dict[str, Any]]) -> FactClaim:
        """Verify an assertion claim by keyword overlap with tool results."""
        keywords = set(claim.claim_text.lower().split()) - {
            "the", "a", "an", "is", "was", "are", "were", "be", "been",
            "has", "have", "had", "do", "does", "did", "will", "would",
            "can", "could", "may", "might", "shall", "should", "to", "of",
            "in", "on", "at", "by", "for", "with", "from", "and", "or",
        }
        if len(keywords) < 3:
            claim.status = GroundingStatus.UNVERIFIABLE
            return claim

        for tool_result in tool_results:
            result_str = json.dumps(tool_result.get("data", {})).lower()
            if not result_str:
                continue
            matches = sum(1 for kw in keywords if kw in result_str)
            if matches >= min(3, len(keywords) * 0.5):
                claim.status = GroundingStatus.GROUNDED
                claim.source_tool = tool_result.get("tool", "unknown")
                claim.anchor = f"Keywords ({matches}/{len(keywords)}) found in tool result"
                claim.confidence = matches / len(keywords)
                claim.verified_at = datetime.now(timezone.utc).isoformat()
                return claim

        return claim

    @classmethod
    def verify_all(cls, claims: List[FactClaim], tool_results: List[Dict[str, Any]]) -> List[FactClaim]:
        """Run verification on all claims."""
        for claim in claims:
            if claim.claim_type == "path":
                cls.verify_path_claim(claim, tool_results)
            elif claim.claim_type == "url":
                cls.verify_url_claim(claim, tool_results)
            elif claim.claim_type == "number":
                cls.verify_number_claim(claim, tool_results)
            elif claim.claim_type == "assertion":
                cls.verify_assertion_claim(claim, tool_results)
        return claims


# ─── Grounding Layer ─────────────────────────────────────────────────────
class GroundingLayer:
    """Main grounding analysis engine for agent outputs.

    Usage:
        layer = GroundingLayer(config)
        report = layer.analyze(output_text, tool_results)
        if not report.threshold_passed:
            // intervene
    """

    def __init__(self, config: Optional[GroundingConfig] = None):
        self.config = config or GroundingConfig()
        self._reports: List[GroundingReport] = []

    def analyze(
        self,
        output_text: str,
        tool_results: Optional[List[Dict[str, Any]]] = None,
        task_id: Optional[str] = None,
    ) -> GroundingReport:
        """Analyze agent output for hallucinated content.

        Args:
            output_text: The full agent output text to check
            tool_results: List of tool execution results to ground against
            task_id: Optional task identifier for logging

        Returns:
            GroundingReport with grounding score and claim analysis
        """
        tool_results = tool_results or []

        # 1. Extract factual claims
        claims = FactExtractor.extract(output_text, self.config)

        # 2. Verify claims against tool results
        if tool_results:
            claims = GroundingVerifier.verify_all(claims, tool_results)

        # 3. Compute grounding score
        total = len(claims) if claims else 1
        grounded = sum(1 for c in claims if c.status == GroundingStatus.GROUNDED)
        contradicted = sum(1 for c in claims if c.status == GroundingStatus.CONTRADICTED)

        if total == 0:
            grounding_score = 1.0  # No factual claims = no hallucination possible
        else:
            # Penalize unsupported claims, heavily penalize contradicted ones
            grounding_score = max(0.0, (grounded - contradicted * 2) / total)

        unsupported = total - grounded - contradicted

        # 4. Determine if threshold is passed
        unsupported_ratio = unsupported / total if total > 0 else 0.0
        threshold_passed = (
            grounding_score >= self.config.score_threshold
            and unsupported_ratio <= self.config.max_unsupported_ratio
        )

        # 5. Generate report
        report = GroundingReport(
            output_snippet=output_text[:500],
            total_claims=total,
            grounded_claims=grounded,
            unsupported_claims=unsupported,
            contradicted_claims=contradicted,
            unverifiable_claims=0,
            grounding_score=round(grounding_score, 4),
            claims=claims,
            threshold_passed=threshold_passed,
            action_taken=self.config.action_on_failure if not threshold_passed else GroundingAction.WARN,
            recommendation=(
                None
                if threshold_passed
                else f"Grounding score {grounding_score:.2f} below threshold {self.config.score_threshold}. "
                     f"{unsupported} of {total} claims ungrounded."
            ),
        )

        self._reports.append(report)

        if not threshold_passed:
            logger.warning(
                f"[GroundingLayer] Hallucination detected for task {task_id}: "
                f"score={grounding_score:.2f}, threshold={self.config.score_threshold}, "
                f"unsupported={unsupported}/{total}"
            )
        else:
            logger.debug(
                f"[GroundingLayer] Output grounded: score={grounding_score:.2f}, "
                f"claims={total}"
            )

        return report

    def sanitize(
        self,
        output_text: str,
        report: GroundingReport,
    ) -> Tuple[str, bool]:
        """Apply grounding report sanctions to output text.

        Returns:
            Tuple of (sanitized_text, was_modified)
        """
        if report.threshold_passed:
            return output_text, False

        action = self.config.action_on_failure

        if action == GroundingAction.WARN:
            return output_text, False

        if action == GroundingAction.ANNOTATE:
            # Add annotations for unsupported claims
            lines = output_text.split("\n")
            annotated = []
            for line in lines:
                annotated.append(line)
                for claim in report.claims:
                    if claim.status == GroundingStatus.UNSUPPORTED and claim.claim_text in line:
                        annotated.append(f"  [⚠ UNSUPPORTED CLAIM: {claim.claim_text[:80]}]")
            return "\n".join(annotated), True

        if action == GroundingAction.REDACT:
            # Remove unsupported claims from output
            sanitized = output_text
            for claim in report.claims:
                if claim.status == GroundingStatus.UNSUPPORTED:
                    sanitized = sanitized.replace(claim.claim_text, "[REDACTED]")
            return sanitized, sanitized != output_text

        if action == GroundingAction.REJECT:
            # Replace output with rejection notice
            return (
                f"[OUTPUT REJECTED] Grounding score {report.grounding_score:.2f} below threshold "
                f"{self.config.score_threshold}. {report.unsupported_claims} unsupported claims found."
            ), True

        return output_text, False

    def get_last_report(self) -> Optional[GroundingReport]:
        return self._reports[-1] if self._reports else None

    def get_report_history(self) -> List[GroundingReport]:
        return list(self._reports)

    def clear_history(self) -> None:
        self._reports.clear()


# ─── Singleton ────────────────────────────────────────────────────────────
_instance: Optional[GroundingLayer] = None


def get_grounding_layer(config: Optional[GroundingConfig] = None) -> GroundingLayer:
    """Get or create the singleton GroundingLayer."""
    global _instance
    if _instance is None:
        _instance = GroundingLayer(config)
    elif config is not None:
        _instance.config = config
    return _instance


def reset_grounding_layer() -> None:
    """Reset the singleton (for testing)."""
    global _instance
    _instance = None
