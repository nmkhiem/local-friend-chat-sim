from __future__ import annotations

import hashlib
import re

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


def comment_prompt(persona: Persona, post_content: str, topic_summary: str) -> str:
    return f"""You are {persona.name}.

Personality: {persona.personality}

Interests: {persona.interests}

Speech style: {persona.speech_style}

The user shared this post:

{post_content}

Topic summary:

{topic_summary}

Write one natural friend-like comment.

Keep it short.

Do not sound like an assistant.

Do not over-explain.

If appropriate, ask a question or gently challenge the idea.
"""


def reply_prompt(persona: Persona, post_content: str, target_comment: str) -> str:
    return f"""You are {persona.name}.

Personality: {persona.personality}

Speech style: {persona.speech_style}

Original post:

{post_content}

Existing comment to reply to:

{target_comment}

Write one short natural reply.

It should sound like a friend replying in a group chat.

Do not repeat the original post.

Do not sound like an assistant.
"""


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


async def generate_comment(
    ollama: OllamaClient,
    persona: Persona,
    post_content: str,
    topic_summary: str,
) -> str:
    generated = await ollama.generate(comment_prompt(persona, post_content, topic_summary))
    return generated or fallback_comment(persona, post_content, topic_summary)


async def generate_reply(
    ollama: OllamaClient,
    persona: Persona,
    post_content: str,
    target_comment: str,
) -> str:
    generated = await ollama.generate(reply_prompt(persona, post_content, target_comment))
    return generated or fallback_reply(persona, target_comment)
