from typing import Dict, Any, List
from .schema import GuardrailSchema, ValidationResult
from ..logs.logger import logger


class OutputValidator:
    def __init__(self):
        self.schema = GuardrailSchema()
    
    async def validate(
        self,
        output: Dict[str, Any]
    ) -> ValidationResult:
        result = self.schema.validate_output(output)
        
        if not result.valid:
            logger.warning(f"Output validation failed: {result.errors}")
        
        return result
    
    async def validate_steps(
        self,
        steps: List[Dict[str, Any]]
    ) -> ValidationResult:
        result = self.schema.validate_steps(steps)
        
        if not result.valid:
            logger.warning(f"Steps validation failed: {result.errors}")
        
        return result
    
def validate_context(
        context: Dict[str, Any]
    ) -> ValidationResult:
    return GuardrailSchema.validate_context(context)


class Guardrails:
    def __init__(self):
        self.validator = OutputValidator()
    
    async def verify_output(self, output: Dict[str, Any]) -> bool:
        result = await self.validator.validate(output)
        return result.valid
    
    async def verify_steps(self, steps: List[Dict[str, Any]]) -> bool:
        result = await self.validator.validate_steps(steps)
        return result.valid
    
    async def check_confidence(
        self,
        confidence: float,
        threshold: float = 0.5
    ) -> bool:
        return confidence >= threshold


guardrails = Guardrails()