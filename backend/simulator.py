from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ollama_client import OllamaClient
from personas import PERSONAS, Persona


COMMENT_COUNTS = (2, 3, 4)
REPLY_COUNTS = (1, 2, 3)


def summarize_topic(content: str) -> str:
    cleaned = " ".join(content.split())
    if len(cleaned) <= 90:
        return cleaned
    words = cleaned.split()
    summary = " ".join(words[:16])
    return f"{summary}..."


def _seed_int(*parts: object) -> int:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def _persona_selection(post_id: int, content: str, counts: tuple[int, ...], purpose: str) -> list[Persona]:
    personas = list(PERSONAS.values())
    seed = _seed_int(post_id, content, purpose)
    count = counts[seed % len(counts)]
    scored = sorted(personas, key=lambda persona: _seed_int(seed, persona.id))
    return scored[:count]


def select_comment_personas(post_id: int, content: str) -> list[Persona]:
    return _persona_selection(post_id, content, COMMENT_COUNTS, "comments")


def select_reply_personas(post_id: int, content: str) -> list[Persona]:
    return _persona_selection(post_id, content, REPLY_COUNTS, "replies")


def comment_batch_prompt(personas: list[Persona], post_content: str, topic_summary: str) -> str:
    personas_json = [
        {
            "persona_id": persona.id,
            "name": persona.name,
            "personality": persona.personality,
            "interests": persona.interests,
            "speech_style": persona.speech_style,
        }
        for persona in personas
    ]
    return f"""You are generating friend-like comments for a local simulated group chat.

Original post:

{post_content}

Topic summary:

{topic_summary}

Personas:

{json.dumps(personas_json, ensure_ascii=False)}

Return only valid JSON.

Return a JSON array.

Each item must have:

- persona_id
- content

Rules:

- One short natural comment per persona.
- Sound like a friend, not an assistant.
- Do not over-explain.
- Do not wrap JSON in markdown.
"""


def reply_batch_prompt(post_content: str, comments: list[dict[str, Any]], reply_tasks: list[dict[str, Any]]) -> str:
    return f"""You are generating short replies in a local simulated group chat.

Original post:

{post_content}

Existing comments:

{json.dumps(comments, ensure_ascii=False)}

Selected reply tasks:

{json.dumps(reply_tasks, ensure_ascii=False)}

Return only valid JSON.

Return a JSON array.

Each item must have:

- persona_id
- parent_comment_id
- content

Rules:

- One short natural reply per task.
- Reply to the target comment.
- Sound like a friend, not an assistant.
- Do not repeat the original post.
- Do not wrap JSON in markdown.
"""


def _extract_json_array(text: str) -> list[Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, list):
        return None
    return parsed


def _clean_content(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    content = " ".join(value.split())
    return content or None


def _fallback_comments(personas: list[Persona], post_content: str, topic_summary: str) -> list[dict[str, str]]:
    return [
        {"persona_id": persona.id, "content": fallback_comment(persona, post_content, topic_summary)}
        for persona in personas
    ]


def _fallback_replies(reply_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "persona_id": task["persona_id"],
            "parent_comment_id": task["parent_comment_id"],
            "content": fallback_reply(PERSONAS[task["persona_id"]], task["target_comment"]),
        }
        for task in reply_tasks
    ]


def _keyword(content: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", content.lower())
    ignored = {"about", "after", "again", "with", "that", "this", "just", "read", "they", "them", "from", "into", "used", "using", "have", "what", "when", "where", "will"}
    for word in words:
        if len(word) > 4 and word not in ignored:
            return word
    return "idea"


def fallback_comment(persona: Persona, post_content: str, topic_summary: str) -> str:
    topic = _keyword(topic_summary or post_content)
    templates = {
        "minh": f"Interesting, but what would make this actually work for {topic} instead of staying theory?",
        "an": f"I like that you are thinking this through. What part of {topic} feels most exciting to you?",
        "huy": f"Okay, this has big late-night brain-tab energy. I am listening.",
        "linh": f"The planning angle is worth unpacking. I wonder what evidence would show it improves decisions.",
        "trang": f"Cool, but where would you apply it first in a real workflow?",
    }
    return templates[persona.id]


def fallback_reply(persona: Persona, target_comment: str) -> str:
    short_target = target_comment.rstrip(".!?")
    templates = {
        "minh": f"Yep, but '{short_target}' needs a concrete test.",
        "an": "That is a good question. I also wonder what the user actually wants from it.",
        "huy": "This thread is getting suspiciously useful.",
        "linh": "Agreed. The next step is defining the assumptions clearly.",
        "trang": "Exactly. Give me one practical use case and I am in.",
    }
    return templates[persona.id]


async def generate_comment_batch(
    ollama: OllamaClient,
    personas: list[Persona],
    post_content: str,
    topic_summary: str,
) -> list[dict[str, str]]:
    generated = await ollama.generate(comment_batch_prompt(personas, post_content, topic_summary))
    if not generated:
        return _fallback_comments(personas, post_content, topic_summary)

    valid_persona_ids = {persona.id for persona in personas}
    parsed = _extract_json_array(generated)
    if parsed is None:
        return _fallback_comments(personas, post_content, topic_summary)

    comments: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in parsed:
        if not isinstance(item, dict):
            return _fallback_comments(personas, post_content, topic_summary)
        persona_id = item.get("persona_id")
        content = _clean_content(item.get("content"))
        if persona_id not in valid_persona_ids or not content or persona_id in seen:
            return _fallback_comments(personas, post_content, topic_summary)
        seen.add(persona_id)
        comments.append({"persona_id": persona_id, "content": content})

    if seen != valid_persona_ids:
        return _fallback_comments(personas, post_content, topic_summary)
    return comments


async def generate_reply_batch(
    ollama: OllamaClient,
    post_content: str,
    comments: list[dict[str, Any]],
    reply_tasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    generated = await ollama.generate(reply_batch_prompt(post_content, comments, reply_tasks))
    if not generated:
        return _fallback_replies(reply_tasks)

    valid_pairs = {(task["persona_id"], task["parent_comment_id"]) for task in reply_tasks}
    parsed = _extract_json_array(generated)
    if parsed is None:
        return _fallback_replies(reply_tasks)

    replies: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for item in parsed:
        if not isinstance(item, dict):
            return _fallback_replies(reply_tasks)
        persona_id = item.get("persona_id")
        parent_comment_id = item.get("parent_comment_id")
        content = _clean_content(item.get("content"))
        pair = (persona_id, parent_comment_id)
        if pair not in valid_pairs or not content or pair in seen:
            return _fallback_replies(reply_tasks)
        seen.add(pair)
        replies.append(
            {
                "persona_id": persona_id,
                "parent_comment_id": parent_comment_id,
                "content": content,
            }
        )

    if seen != valid_pairs:
        return _fallback_replies(reply_tasks)
    return replies
