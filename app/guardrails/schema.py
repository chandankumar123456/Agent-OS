from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from enum import Enum


class ValidationType(str, Enum):
    SCHEMA = "schema"
    LOGICAL = "logical"
    CONSTRAINT = "constraint"


class ValidationResult(BaseModel):
    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    confidence: float = 1.0


class OutputSchema(BaseModel):
    result: Optional[Any] = None
    status: str = "success"
    details: Optional[Dict[str, Any]] = None


class GuardrailSchema:
    @staticmethod
    def validate_output(output: Dict[str, Any]) -> ValidationResult:
        errors = []
        warnings = []
        
        if not output:
            errors.append("Output is empty")
            return ValidationResult(
                valid=False,
                errors=errors,
                confidence=0.0
            )
        
        if "status" in output:
            if output["status"] not in ["success", "failure", "pending"]:
                errors.append(f"Invalid status: {output['status']}")
        
        if "result" in output and not output["result"]:
            warnings.append("Result is empty")
        
        is_valid = len(errors) == 0
        confidence = 1.0 - (len(errors) * 0.3) - (len(warnings) * 0.1)
        
        return ValidationResult(
            valid=is_valid,
            errors=errors,
            warnings=warnings,
            confidence=max(0.0, confidence)
        )
    
    @staticmethod
    def validate_steps(steps: List[Dict[str, Any]]) -> ValidationResult:
        errors = []
        
        if not steps:
            errors.append("No steps in workflow")
            return ValidationResult(valid=False, errors=errors)
        
        for i, step in enumerate(steps):
            if "step" not in step:
                errors.append(f"Step {i} missing 'step' field")
            if "agent_type" not in step:
                errors.append(f"Step {i} missing 'agent_type' field")
        
        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            confidence=1.0 if len(errors) == 0 else 0.5
        )
    
    @staticmethod
    def validate_context(context: Dict[str, Any]) -> ValidationResult:
        warnings = []
        
        if not context:
            warnings.append("Context is empty")
        
        if "query" not in context:
            warnings.append("Context missing 'query'")
        
        return ValidationResult(
            valid=True,
            warnings=warnings,
            confidence=1.0 - (len(warnings) * 0.2)
        )