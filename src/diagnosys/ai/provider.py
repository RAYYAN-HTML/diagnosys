from abc import ABC, abstractmethod
from typing import Optional
from diagnosys.models.diagnostics import DiagnosisResult

class AIProvider(ABC):
    @abstractmethod
    def explain(self, result: DiagnosisResult) -> str:
        """Takes a deterministic diagnosis and returns a natural language explanation."""
        pass

class NoAIProvider(AIProvider):
    def explain(self, result: DiagnosisResult) -> str:
        return "AI explanation is disabled. Please refer to the standard deterministic evidence."

class DummyAIProvider(AIProvider):
    """A mock provider for testing that formats the data into a string."""
    def explain(self, result: DiagnosisResult) -> str:
        if not result.primary_hypothesis:
            return "The system looks completely healthy based on the provided evidence."
        
        category = result.primary_hypothesis.category.replace("_", " ").title()
        return f"Based on the evidence, your system is experiencing {category}. I recommend following the standard checks."
