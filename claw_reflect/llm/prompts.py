"""Central prompt templates and strict JSON parsing helpers."""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from claw_reflect.llm.base import LLMMessage, LLMResponse

T = TypeVar("T", bound=BaseModel)


class ReflectError(Exception):
    """Raised when an LLM response cannot be parsed/validated."""


class PromptLibrary:
    JSON_ONLY_SUFFIX = (
        "Respond ONLY with valid JSON matching the schema exactly. "
        "No prose, no markdown, no surrounding code fences, no extra keys."
    )

    @classmethod
    def summarise_session(cls, memories: list[str], agent_id: str) -> list[LLMMessage]:
        system = (
            "You are a memory distillation engine. Given raw agent memory entries, "
            "produce a concise factual summary. Respond only in JSON: "
            "{summary: str, key_facts: list[str], topics: list[str], confidence: float}. "
            + cls.JSON_ONLY_SUFFIX
        )
        lines = [f"- [{idx + 1}] {entry}" for idx, entry in enumerate(memories)]
        user = (
            f"agent_id: {agent_id}\n"
            "Raw memory entries (timestamped):\n"
            f"{chr(10).join(lines)}"
        )
        return [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)]

    @classmethod
    def extract_preferences(cls, memories: list[str], existing_prefs: dict) -> list[LLMMessage]:
        system = (
            "Extract durable user preferences, habits, and dislikes from the memory entries. "
            "Infer cautiously and include reasoning. "
            "Schema: {preferences: [{category: str, key: str, value: any, confidence: float, reasoning: str}]}. "
            + cls.JSON_ONLY_SUFFIX
        )
        user = (
            "Existing active preferences by category:\n"
            f"{json.dumps(existing_prefs, ensure_ascii=True)}\n\n"
            "New memory entries:\n"
            + "\n".join(f"- {entry}" for entry in memories)
        )
        return [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)]

    @classmethod
    def detect_contradictions(cls, memory_a: str, memory_b: str) -> list[LLMMessage]:
        system = (
            "Determine if two memory statements contradict each other factually. "
            "Schema: {contradicts: bool, field: str | null, explanation: str, confidence: float}. "
            + cls.JSON_ONLY_SUFFIX
        )
        user = f"memory_a:\n{memory_a}\n\nmemory_b:\n{memory_b}"
        return [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)]

    @classmethod
    def resolve_contradiction(cls, contradiction: dict, strategy: str) -> list[LLMMessage]:
        system = (
            "Resolve a contradiction between two conflicting values according to strategy. "
            "Schema: {resolved_value: any, reasoning: str}. "
            + cls.JSON_ONLY_SUFFIX
        )
        user = (
            f"strategy: {strategy}\n"
            f"contradiction: {json.dumps(contradiction, ensure_ascii=True)}"
        )
        return [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)]

    @classmethod
    def score_importance(cls, memory: str, context: dict) -> list[LLMMessage]:
        system = (
            "Rate long-term importance of a memory from 0.0 to 1.0. "
            "Schema: {score: float, reasoning: str, factors: list[str]}. "
            + cls.JSON_ONLY_SUFFIX
        )
        user = f"memory:\n{memory}\n\ncontext:\n{json.dumps(context, ensure_ascii=True)}"
        return [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)]

    @classmethod
    def check_duplicate(cls, memory_a: str, memory_b: str) -> list[LLMMessage]:
        system = (
            "Determine semantic duplication between two memory records. "
            "Schema: {is_duplicate: bool, similarity_score: float, keep_which: \"a\" | \"b\" | \"merge\", "
            "merged_content: str | null}. "
            + cls.JSON_ONLY_SUFFIX
        )
        user = f"memory_a:\n{memory_a}\n\nmemory_b:\n{memory_b}"
        return [LLMMessage(role="system", content=system), LLMMessage(role="user", content=user)]


def parse_json_response(response: LLMResponse, schema_class: type[T]) -> T:
    raw = response.content.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReflectError(f"Invalid JSON response: {exc}") from exc

    try:
        return schema_class.model_validate(parsed)
    except ValidationError as exc:
        raise ReflectError(f"Response schema validation failed: {exc}") from exc
