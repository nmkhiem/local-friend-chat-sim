from __future__ import annotations

import hashlib
import json
from typing import Any

from ollama_client import OllamaClient
from personas import Council, Persona


COMMENT_COUNTS = (2, 3)
REPLY_COUNTS = (1, 2)
MAX_MESSAGE_CHARS = 520
MAX_SUMMARY_CHARS = 900
MAX_MEMORY_CHARS = 1000


class GenerationError(RuntimeError):
    pass


def summarize_topic(content: str) -> str:
    cleaned = " ".join(content.split())
    if len(cleaned) <= 90:
        return cleaned
    words = cleaned.split()
    summary = " ".join(words[:16])
    return f"{summary}..."


def select_comment_personas(post_id: int, content: str, personas: list[Persona]) -> list[Persona]:
    return _persona_selection(post_id, content, COMMENT_COUNTS, "comments", personas)


def select_reply_personas(post_id: int, content: str, personas: list[Persona]) -> list[Persona]:
    return _persona_selection(post_id, content, REPLY_COUNTS, "replies", personas)


def comment_batch_prompt(council: Council, personas: list[Persona], post_content: str, topic_summary: str) -> str:
    return f"""Generate council-chat comments.

Council: {council.name}
Purpose: {council.description}
Style: {council.simulation_style}

Original post:
{post_content}

Topic summary: {topic_summary}

Personas to write for:
{_persona_lines(personas)}

Rules:
- Return strict JSON only.
- Use the same language as the original post.
- Write exactly one short natural comment for each listed persona_id.
- Each comment must react to a concrete detail from the original post.
- Sound like a person in a chat, not an assistant.
- Keep each content under 60 words.

Output shape:
{{"comments":[{{"persona_id":"persona_id_here","content":"comment here"}}]}}
"""


def reply_batch_prompt(
    council: Council,
    post_content: str,
    comments: list[dict[str, Any]],
    reply_tasks: list[dict[str, Any]],
) -> str:
    return f"""Generate council-chat replies.

Council: {council.name}
Purpose: {council.description}
Style: {council.simulation_style}

Original post:
{post_content}

Existing discussion:
{_comment_lines(comments)}

Reply tasks:
{_reply_task_lines(reply_tasks)}

Rules:
- Return strict JSON only.
- Use the same language as the original post.
- Write exactly one short reply for each task.
- Use the given persona_id and parent_comment_id exactly.
- Reply to the target comment, not just the original post.
- Do not duplicate an existing comment.
- Sound like a person in a chat, not an assistant.
- Keep each content under 50 words.

Output shape:
{{"replies":[{{"persona_id":"persona_id_here","parent_comment_id":123,"content":"reply here"}}]}}
"""


def summary_prompt(council: Council, post_content: str, comments: list[dict[str, Any]]) -> str:
    return f"""Summarize this local council discussion.

Council: {council.name}
Purpose: {council.description}
Style: {council.simulation_style}

Original post:
{post_content}

Discussion:
{_comment_lines(comments)}

Return strict JSON only. Return one JSON object with:

- key_points: array of 2 to 4 short strings
- open_questions: array of 1 to 3 short strings
- next_step: one short string

Keep it practical and under 180 words total. Do not wrap JSON in markdown.
"""


def memory_update_prompt(
    council: Council,
    personas: list[Persona],
    post_content: str,
    discussion_summary: str,
    comments: list[dict[str, Any]],
) -> str:
    return f"""Update concise local memory for each participating persona.

Council: {council.name}
Purpose: {council.description}

Original post:
{post_content}

Discussion summary:
{discussion_summary}

Recent discussion:
{_comment_lines(comments[-24:])}

Personas:
{_memory_persona_lines(personas)}

Rules:
- Return strict JSON only.
- Summarize old_memory plus this discussion.
- Keep memory about the user's recurring topics, preferences, and useful context.
- Do not store private secrets or exact long quotes.
- Keep each memory under 1000 characters.

Output shape:
{{"memories":[{{"persona_id":"persona_id_here","memory":"memory here"}}]}}
"""


async def generate_comment_batch(
    ollama: OllamaClient,
    council: Council,
    personas: list[Persona],
    post_content: str,
    topic_summary: str,
) -> list[dict[str, str]]:
    generated = await ollama.generate(comment_batch_prompt(council, personas, post_content, topic_summary))

    valid_persona_ids = {persona.id for persona in personas}
    parsed = _extract_json_items(generated, "comments")
    if parsed is None:
        raise GenerationError('Comment generation returned invalid JSON. Expected {"comments":[...]}.')

    comments: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in parsed:
        if not isinstance(item, dict):
            raise GenerationError("Comment generation returned an invalid item.")
        item = _normalize_item_keys(item)
        persona_id = item.get("persona_id")
        content = _clean_content(item.get("content"), MAX_MESSAGE_CHARS)
        if persona_id not in valid_persona_ids or not content or persona_id in seen:
            raise GenerationError("Comment generation returned invalid persona IDs or empty content.")
        seen.add(persona_id)
        comments.append({"persona_id": persona_id, "content": content})

    if not comments:
        raise GenerationError("Comment generation did not return any valid comments.")
    return comments


async def generate_reply_batch(
    ollama: OllamaClient,
    council: Council,
    personas: list[Persona],
    post_content: str,
    comments: list[dict[str, Any]],
    reply_tasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    generated = await ollama.generate(reply_batch_prompt(council, post_content, comments, reply_tasks))

    valid_pairs = {(task["persona_id"], task["parent_comment_id"]) for task in reply_tasks}
    parsed = _extract_json_items(generated, "replies")
    if parsed is None:
        raise GenerationError('Reply generation returned invalid JSON. Expected {"replies":[...]}.')

    replies: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    parent_by_persona: dict[str, int] = {}
    for task in reply_tasks:
        persona_id = task["persona_id"]
        if persona_id in parent_by_persona:
            parent_by_persona[persona_id] = -1
        else:
            parent_by_persona[persona_id] = task["parent_comment_id"]

    for item in parsed:
        if not isinstance(item, dict):
            raise GenerationError("Reply generation returned an invalid item.")
        item = _normalize_item_keys(item)
        persona_id = item.get("persona_id")
        parent_comment_id = item.get("parent_comment_id")
        content = _clean_content(item.get("content"), MAX_MESSAGE_CHARS)
        pair = (persona_id, parent_comment_id)
        if pair not in valid_pairs and persona_id in parent_by_persona and parent_by_persona[persona_id] > 0:
            parent_comment_id = parent_by_persona[persona_id]
            pair = (persona_id, parent_comment_id)
        if pair not in valid_pairs or not content or pair in seen:
            raise GenerationError("Reply generation returned invalid parent/persona pairs or empty content.")
        seen.add(pair)
        replies.append(
            {
                "persona_id": persona_id,
                "parent_comment_id": parent_comment_id,
                "content": content,
            }
        )

    if not replies:
        raise GenerationError("Reply generation did not return any valid replies.")
    return replies


async def generate_discussion_summary(
    ollama: OllamaClient,
    council: Council,
    post_content: str,
    comments: list[dict[str, Any]],
) -> str:
    if not comments:
        return ""

    generated = await ollama.generate(summary_prompt(council, post_content, comments[-40:]))
    parsed = _extract_json_object(generated)
    summary = _summary_from_json(parsed)
    if summary:
        return summary

    raise GenerationError("Summary generation returned invalid JSON.")


async def generate_memory_updates(
    ollama: OllamaClient,
    council: Council,
    personas: list[Persona],
    post_content: str,
    discussion_summary: str,
    comments: list[dict[str, Any]],
) -> dict[str, str]:
    if not personas or not comments:
        return {}

    generated = await ollama.generate(
        memory_update_prompt(council, personas, post_content, discussion_summary, comments)
    )
    parsed = _extract_json_items(generated, "memories")
    if parsed is None:
        raise GenerationError('Memory generation returned invalid JSON. Expected {"memories":[...]}.')

    return _memory_updates_from_json(parsed, {persona.id for persona in personas})


def _seed_int(*parts: object) -> int:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def _persona_selection(
    post_id: int,
    content: str,
    counts: tuple[int, ...],
    purpose: str,
    personas: list[Persona],
) -> list[Persona]:
    available = [persona for persona in personas if persona.is_active] or personas
    if not available:
        return []
    seed = _seed_int(post_id, content, purpose)
    count = min(len(available), counts[seed % len(counts)])
    scored = sorted(available, key=lambda persona: _seed_int(seed, persona.id))
    return scored[:count]


def _persona_lines(personas: list[Persona]) -> str:
    lines = []
    for persona in personas:
        memory = persona.memory[-260:] if persona.memory else "none"
        lines.append(
            "- "
            f"persona_id={persona.id}; name={persona.name}; role={persona.role}; "
            f"personality={persona.personality}; speech_style={persona.speech_style}; memory={memory}"
        )
    return "\n".join(lines)


def _memory_persona_lines(personas: list[Persona]) -> str:
    lines = []
    for persona in personas:
        memory = persona.memory[-500:] if persona.memory else "none"
        lines.append(f"- persona_id={persona.id}; name={persona.name}; role={persona.role}; old_memory={memory}")
    return "\n".join(lines)


def _comment_lines(comments: list[dict[str, Any]]) -> str:
    if not comments:
        return "none"
    lines = []
    for comment in comments:
        parent = comment.get("parent_comment_id") or "root"
        name = comment.get("persona_name") or comment.get("author_name") or comment.get("persona_id")
        lines.append(
            f"- id={comment['id']}; parent={parent}; persona={comment.get('persona_id')}; "
            f"name={name}; content={comment['content']}"
        )
    return "\n".join(lines)


def _reply_task_lines(reply_tasks: list[dict[str, Any]]) -> str:
    lines = []
    for task in reply_tasks:
        memory = task.get("memory", "")[-220:] or "none"
        lines.append(
            "- "
            f"persona_id={task['persona_id']}; name={task['persona_name']}; role={task['role']}; "
            f"parent_comment_id={task['parent_comment_id']}; target={task['target_comment']}; "
            f"speech_style={task['speech_style']}; memory={memory}"
        )
    return "\n".join(lines)


def _extract_json_array(text: str) -> list[Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, list):
        return None
    return parsed


def _extract_json_items(text: str, key: str) -> list[Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None

    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        parsed = _normalize_item_keys(parsed)
        value = parsed.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [value]
    return None


def _extract_json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None
    return parsed


def _normalize_item_keys(item: dict[str, Any]) -> dict[str, Any]:
    return {key.strip() if isinstance(key, str) else key: value for key, value in item.items()}


def _clean_content(value: Any, max_chars: int) -> str | None:
    if not isinstance(value, str):
        return None
    content = " ".join(value.split())
    if not content:
        return None
    return content[:max_chars].rstrip()


def _summary_from_json(value: dict[str, Any] | None) -> str | None:
    if not value:
        return None
    key_points = _clean_string_list(value.get("key_points"), 4)
    open_questions = _clean_string_list(value.get("open_questions"), 3)
    next_step = _clean_content(value.get("next_step"), 180)
    if not key_points or not next_step:
        return None

    lines = ["Key points:"]
    lines.extend(f"- {point}" for point in key_points)
    lines.append("")
    lines.append("Open questions:")
    if open_questions:
        lines.extend(f"- {question}" for question in open_questions)
    else:
        lines.append("- What should be tested next?")
    lines.append("")
    lines.append("Next step:")
    lines.append(f"- {next_step}")
    return "\n".join(lines)[:MAX_SUMMARY_CHARS].rstrip()


def _memory_updates_from_json(items: list[Any], valid_persona_ids: set[str]) -> dict[str, str]:
    updates: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            raise GenerationError("Memory generation returned an invalid item.")
        item = _normalize_item_keys(item)
        persona_id = item.get("persona_id")
        memory = _clean_content(item.get("memory"), MAX_MEMORY_CHARS)
        if persona_id not in valid_persona_ids or memory is None:
            raise GenerationError("Memory generation returned invalid persona IDs or empty memory.")
        updates[persona_id] = memory
    if not updates:
        raise GenerationError("Memory generation did not return any valid memories.")
    return updates


def _clean_string_list(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value[:limit]:
        content = _clean_content(item, 180)
        if content:
            cleaned.append(content)
    return cleaned
