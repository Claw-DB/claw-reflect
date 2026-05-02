"""PromptLibrary — centralised repository of system and user prompt templates."""

from __future__ import annotations

SUMMARISE_SYSTEM = (
    "You are a memory distillation engine. "
    "Summarise the following agent memory records into a single compact, factual paragraph. "
    "Preserve the most important facts, preferences, and patterns. "
    "Output only the summary — no commentary."
)

EXTRACT_PREFERENCES_SYSTEM = (
    "You are a preference extraction engine. "
    "Analyse the memory records and extract explicit or implied agent preferences. "
    "Return a JSON array of objects with keys: category, key, value, confidence (0-1)."
)

DETECT_CONTRADICTIONS_SYSTEM = (
    "You are a contradiction detection engine. "
    "Compare the following pairs of memory records and identify conflicting claims. "
    "Return a JSON array of objects with keys: field, value_a, value_b, confidence (0-1)."
)


class PromptLibrary:
    """Provides system and user prompt strings for each pipeline stage."""

    summarise_system: str = SUMMARISE_SYSTEM
    extract_preferences_system: str = EXTRACT_PREFERENCES_SYSTEM
    detect_contradictions_system: str = DETECT_CONTRADICTIONS_SYSTEM

    @staticmethod
    def summarise_user(memories: list[str]) -> str:
        """Build the user message for the summarisation prompt."""
        joined = "\n---\n".join(memories)
        return f"Memory records to summarise:\n\n{joined}"

    @staticmethod
    def extract_preferences_user(memories: list[str]) -> str:
        """Build the user message for the preference extraction prompt."""
        joined = "\n---\n".join(memories)
        return f"Memory records to analyse:\n\n{joined}"
