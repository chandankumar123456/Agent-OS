import re
from typing import Set
from .models import Capability, CapabilityAssessment, ExecutionEnvironment

BROWSER_UI_KEYWORDS = [
    "open chrome", "open browser", "launch browser", "launch chrome",
    "search in browser", "search on google", "search in chrome", "google search",
    "login to", "sign in to", "log in to", "fill form", "fill out form",
    "click button", "click link", "navigate to", "go to website", "browse to",
    "screenshot", "capture page", "take screenshot", "scroll down", "scroll up",
    "type in", "enter text", "submit form", "refresh page", "go back",
]

SHELL_KEYWORDS = [
    "shell", "command", "terminal", "bash", "powershell", "cmd",
    "run command", "execute command", "install ", "git ", "docker ", "npm ", "pip ",
]

FILE_KEYWORDS = [
    "read file", "write file", "edit file", "create file", "delete file",
    "list directory", "search files", "file content", "save file",
]


class ExecutionEnvironmentSelector:
    def select(self, query: str, assessment: CapabilityAssessment) -> ExecutionEnvironment:
        q = query.lower()

        for kw in BROWSER_UI_KEYWORDS:
            if kw in q:
                return ExecutionEnvironment.BROWSER_UI

        for kw in SHELL_KEYWORDS:
            if kw in q:
                return ExecutionEnvironment.SHELL

        for kw in FILE_KEYWORDS:
            if kw in q:
                return ExecutionEnvironment.FILE

        primary = assessment.primary_capability
        if primary == Capability.WEB:
            return ExecutionEnvironment.CLOUD_API
        elif primary == Capability.SHELL:
            return ExecutionEnvironment.SHELL
        elif primary == Capability.FILE:
            return ExecutionEnvironment.FILE
        elif primary == Capability.CODE:
            return ExecutionEnvironment.SANDBOX
        elif primary == Capability.DEPLOYMENT:
            return ExecutionEnvironment.SHELL

        return ExecutionEnvironment.LOCAL


environment_selector = ExecutionEnvironmentSelector()
