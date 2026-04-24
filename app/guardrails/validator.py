from typing import Dict, Any, List
from .schema import GuardrailSchema, ValidationResult, CustomRule
from ..logs.logger import logger


class OutputValidator:
    def __init__(self):
        self.schema = GuardrailSchema()
    
    async def validate(
        self,
        output: Dict[str, Any],
        rules: List[CustomRule] = None
    ) -> ValidationResult:
        result = self.schema.validate_output(output)
        
        if rules:
            custom_result = self.schema.validate_with_rules(output, rules)
            result.errors.extend(custom_result.errors)
            result.warnings.extend(custom_result.warnings)
            result.valid = len(result.errors) == 0
            result.confidence = max(0.0, result.confidence - (len(custom_result.errors) * 0.3) - (len(custom_result.warnings) * 0.1))
        
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


def validate_context(context: Dict[str, Any]) -> ValidationResult:
    return GuardrailSchema.validate_context(context)


class Guardrails:
    def __init__(self):
        self.validator = OutputValidator()
    
    async def verify_output(self, output: Dict[str, Any]) -> bool:
        # 1. Run existing schema validation
        result = await self.validator.validate(output)
        
        # 2. Load active rules from DB (optional, resilient)
        rules = []
        try:
            from ..memory.long_term import guardrail_rule_repo
            active_rules = await guardrail_rule_repo.list_active()
            rules = [
                CustomRule(
                    name=rule.name,
                    rule_type=rule.rule_type,
                    condition=rule.condition or {},
                    action=rule.action,
                )
                for rule in active_rules
            ]
        except Exception as e:
            logger.debug(f"Guardrail rule DB load skipped or failed: {e}")
        
        # 3. Run custom rule validation if rules loaded
        if rules:
            custom_result = GuardrailSchema.validate_with_rules(output, rules)
            result.errors.extend(custom_result.errors)
            result.warnings.extend(custom_result.warnings)
            result.valid = len(result.errors) == 0
            result.confidence = max(0.0, result.confidence - (len(custom_result.errors) * 0.3) - (len(custom_result.warnings) * 0.1))
        
        # 4. Combine and return
        if not result.valid:
            logger.warning(f"Output validation failed: {result.errors}")
        
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