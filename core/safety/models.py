from enum import Enum


class ActionSeverity(str, Enum):
    SAFE = "safe"
    WARNING = "warning"
    IRREVERSIBLE = "irreversible"
