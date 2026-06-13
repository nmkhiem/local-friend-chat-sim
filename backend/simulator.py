from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ollama_client import OllamaClient
from personas import Council, Persona


COMMENT_COUNTS = (3, 4, 5)
REPLY_COUNTS = (2, 3, 4)
MAX_MESSAGE_CHARS = 520
MAX_SUMMARY_CHARS = 900
MAX_MEMORY_CHARS = 1000


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
    return f"""You are simulating a local-first council chat.

Council:

{json.dumps(_council_payload(council), ensure_ascii=False)}

Original post:

{post_content}

Topic summary:

{topic_summary}

Personas:

{json.dumps([_persona_payload(persona) for persona in personas], ensure_ascii=False)}

Return strict JSON only. Return a JSON array.

Each item must have exactly:

- persona_id
- content

Rules:

- Write one short natural comment per persona.
- Follow the council simulation_style.
- Use persona profile and memory, but do not mention memory.
- Sound like a person in a chat, not an assistant.
- Keep each content under 80 words.
- Do not wrap JSON in markdown.
"""


def reply_batch_prompt(
    council: Council,
    post_content: str,
    comments: list[dict[str, Any]],
    reply_tasks: list[dict[str, Any]],
) -> str:
    return f"""You are simulating short replies in a local-first council chat.

Council:

{json.dumps(_council_payload(council), ensure_ascii=False)}

Original post:

{post_content}

Existing comments:

{json.dumps(comments, ensure_ascii=False)}

Selected reply tasks:

{json.dumps(reply_tasks, ensure_ascii=False)}

Return strict JSON only. Return a JSON array.

Each item must have exactly:

- persona_id
- parent_comment_id
- content

Rules:

- Write one short natural reply per task.
- Reply to the target comment, not just the original post.
- Follow the council simulation_style.
- Use persona profile and memory, but do not mention memory.
- Do not duplicate an existing comment.
- Sound like a person in a chat, not an assistant.
- Keep each content under 70 words.
- Do not wrap JSON in markdown.
"""


def summary_prompt(council: Council, post_content: str, comments: list[dict[str, Any]]) -> str:
    return f"""Summarize this local council discussion.

Council:

{json.dumps(_council_payload(council), ensure_ascii=False)}

Original post:

{post_content}

Discussion:

{json.dumps(comments, ensure_ascii=False)}

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
    payload = [
        {
            "persona_id": persona.id,
            "name": persona.name,
            "role": persona.role,
            "old_memory": persona.memory,
        }
        for persona in personas
    ]
    return f"""Update concise local memory for each participating persona.

Council:

{json.dumps(_council_payload(council), ensure_ascii=False)}

Original post:

{post_content}

Discussion summary:

{discussion_summary}

Recent discussion:

{json.dumps(comments[-24:], ensure_ascii=False)}

Personas:

{json.dumps(payload, ensure_ascii=False)}

Return strict JSON only. Return a JSON array.

Each item must have exactly:

- persona_id
- memory

Rules:

- Summarize old_memory plus this discussion.
- Keep memory about the user's recurring topics, preferences, and useful context.
- Do not store private secrets or exact long quotes.
- Keep each memory under 1000 characters.
- Do not wrap JSON in markdown.
"""


async def generate_comment_batch(
    ollama: OllamaClient,
    council: Council,
    personas: list[Persona],
    post_content: str,
    topic_summary: str,
) -> list[dict[str, str]]:
    generated = await ollama.generate(comment_batch_prompt(council, personas, post_content, topic_summary))
    if not generated:
        return _fallback_comments(council, personas, post_content, topic_summary)

    valid_persona_ids = {persona.id for persona in personas}
    parsed = _extract_json_array(generated)
    if parsed is None:
        return _fallback_comments(council, personas, post_content, topic_summary)

    comments: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in parsed:
        if not isinstance(item, dict):
            return _fallback_comments(council, personas, post_content, topic_summary)
        persona_id = item.get("persona_id")
        content = _clean_content(item.get("content"), MAX_MESSAGE_CHARS)
        if persona_id not in valid_persona_ids or not content or persona_id in seen:
            return _fallback_comments(council, personas, post_content, topic_summary)
        seen.add(persona_id)
        comments.append({"persona_id": persona_id, "content": content})

    if seen != valid_persona_ids:
        return _fallback_comments(council, personas, post_content, topic_summary)
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
    if not generated:
        return _fallback_replies(council, personas, reply_tasks)

    valid_pairs = {(task["persona_id"], task["parent_comment_id"]) for task in reply_tasks}
    parsed = _extract_json_array(generated)
    if parsed is None:
        return _fallback_replies(council, personas, reply_tasks)

    replies: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for item in parsed:
        if not isinstance(item, dict):
            return _fallback_replies(council, personas, reply_tasks)
        persona_id = item.get("persona_id")
        parent_comment_id = item.get("parent_comment_id")
        content = _clean_content(item.get("content"), MAX_MESSAGE_CHARS)
        pair = (persona_id, parent_comment_id)
        if pair not in valid_pairs or not content or pair in seen:
            return _fallback_replies(council, personas, reply_tasks)
        seen.add(pair)
        replies.append(
            {
                "persona_id": persona_id,
                "parent_comment_id": parent_comment_id,
                "content": content,
            }
        )

    if seen != valid_pairs:
        return _fallback_replies(council, personas, reply_tasks)
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
    if generated:
        parsed = _extract_json_object(generated)
        summary = _summary_from_json(parsed)
        if summary:
            return summary

    return _fallback_summary(council, post_content, comments)


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
    if generated:
        parsed = _extract_json_array(generated)
        if parsed is not None:
            updates = _memory_updates_from_json(parsed, {persona.id for persona in personas})
            if updates:
                return updates

    return {persona.id: _fallback_memory(persona, council, post_content, discussion_summary) for persona in personas}


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


def _council_payload(council: Council) -> dict[str, Any]:
    return {
        "id": council.id,
        "name": council.name,
        "description": council.description,
        "simulation_style": council.simulation_style,
    }


def _persona_payload(persona: Persona) -> dict[str, Any]:
    return {
        "persona_id": persona.id,
        "name": persona.name,
        "avatar_label": persona.avatar_label,
        "role": persona.role,
        "personality": persona.personality,
        "interests": persona.interests,
        "speech_style": persona.speech_style,
        "memory": persona.memory,
    }


def _extract_json_array(text: str) -> list[Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, list):
        return None
    return parsed


def _extract_json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None
    return parsed


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
            return {}
        persona_id = item.get("persona_id")
        memory = _clean_content(item.get("memory"), MAX_MEMORY_CHARS)
        if persona_id not in valid_persona_ids or memory is None:
            return {}
        updates[persona_id] = memory
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


def _fallback_comments(
    council: Council,
    personas: list[Persona],
    post_content: str,
    topic_summary: str,
) -> list[dict[str, str]]:
    return [
        {"persona_id": persona.id, "content": fallback_comment(council, persona, post_content, topic_summary)}
        for persona in personas
    ]


def _fallback_replies(
    council: Council,
    personas: list[Persona],
    reply_tasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    personas_by_id = {persona.id: persona for persona in personas}
    replies: list[dict[str, Any]] = []
    for task in reply_tasks:
        persona = personas_by_id.get(task["persona_id"])
        if persona is None:
            continue
        replies.append(
            {
                "persona_id": task["persona_id"],
                "parent_comment_id": task["parent_comment_id"],
                "content": fallback_reply(council, persona, task["target_comment"]),
            }
        )
    return replies


def _keyword(content: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", content.lower())
    ignored = {
        "about",
        "after",
        "again",
        "with",
        "that",
        "this",
        "just",
        "read",
        "they",
        "them",
        "from",
        "into",
        "used",
        "using",
        "have",
        "what",
        "when",
        "where",
        "will",
        "want",
        "could",
        "explore",
        "world",
        "models",
    }
    for word in words:
        if len(word) > 4 and word not in ignored:
            return word
    return "idea"


def fallback_comment(council: Council, persona: Persona, post_content: str, topic_summary: str) -> str:
    topic = _keyword(topic_summary or post_content)
    friend_templates = {
        "minh": f"Interesting, but what would make this actually work for {topic} instead of staying theory?",
        "an": f"I like that you are thinking this through. What part of {topic} feels most alive to you?",
        "huy": "Okay, this has big late-night brain-tab energy. I am listening.",
        "linh": f"The planning angle is worth unpacking. What evidence would show {topic} improves decisions?",
        "trang": f"Cool, but where would you apply {topic} first in a real workflow?",
    }
    if council.id == "friend" and persona.id in friend_templates:
        return friend_templates[persona.id]

    if council.id == "research":
        templates = {
            "advisor": f"I would sharpen the claim around {topic}: what exactly becomes possible that was not before?",
            "reviewer_2": f"The weak assumption is probably evaluation. What baseline would make {topic} look less impressive?",
            "engineer": f"I would ask what data path breaks first. Healthcare systems are rarely clean enough for {topic} demos.",
            "statistician": f"Be careful about causality here. What outcome proves {topic} helps beyond correlation?",
            "curious_peer": f"This is interesting. Is the core bet better prediction, better planning, or better clinician feedback?",
        }
        return templates.get(persona.id, f"My {persona.role} take: test the evidence behind {topic} before widening the claim.")

    if council.id == "product":
        templates = {
            "product_thinker": f"I would pick one painful workflow for {topic} and prove it saves time there first.",
            "ux_friend": f"What would the first screen ask the user to do? That moment decides whether {topic} feels useful.",
            "skeptical_engineer": f"Scope this down hard. What is the smallest {topic} version that still teaches you something?",
            "early_user": f"I would try it if it solves one annoying task immediately, not if I have to configure a whole system.",
            "business_realist": f"Who keeps paying after week two? That is the real test for {topic}.",
        }
        return templates.get(persona.id, f"My {persona.role} angle: tie {topic} to one user problem and one feasibility test.")

    if council.id == "study":
        templates = {
            "tutor": f"Start by separating the definition of {topic} from the use case. Those often get mixed together.",
            "example_maker": f"A tiny example would help: imagine {topic} as a decision map with one input and one next move.",
            "quizzer": f"Quick check: what would you expect to happen if the main assumption behind {topic} is false?",
            "misconception_checker": f"One possible trap is treating {topic} as magic prediction instead of a model with limits.",
            "note_taker": f"Notes version: define it, name the assumption, test with one example, then compare alternatives.",
        }
        return templates.get(persona.id, f"For learning {topic}, I would use one example, one misconception, and one check question.")

    if council.id == "harsh_review":
        templates = {
            "reviewer_2": f"This is too broad as stated. Name the falsifiable claim for {topic}.",
            "skeptical_engineer": f"Cut the scope. If the first prototype needs perfect data, it is already in trouble.",
            "practical_realist": f"The useful next step is not more framing. Pick one test and one failure criterion.",
            "evidence_checker": f"What evidence would change your mind? If none, {topic} is not ready for serious critique.",
            "concise_summarizer": f"Bottom line: make the claim smaller, test it faster, and write down what would prove it wrong.",
        }
        return templates.get(persona.id, f"Direct take: narrow {topic}, define the evidence, and decide the next test.")

    return f"My {persona.role} take: {topic} needs one concrete example and one clear next step."


def fallback_reply(council: Council, persona: Persona, target_comment: str) -> str:
    short_target = target_comment.rstrip(".!?")
    if len(short_target) > 80:
        short_target = f"{short_target[:77].rstrip()}..."

    if council.id == "friend":
        templates = {
            "minh": f"Yep, but '{short_target}' needs a concrete test.",
            "an": "That is a good question. I also wonder what the user actually wants from it.",
            "huy": "This thread is getting suspiciously useful.",
            "linh": "Agreed. The next step is defining the assumptions clearly.",
            "trang": "Exactly. Give me one practical use case and I am in.",
        }
        return templates.get(persona.id, "I agree, but I would make the next step more concrete.")

    if council.id == "research":
        templates = {
            "advisor": "That gets stronger if you state the claim as the decision it improves.",
            "reviewer_2": f"I still would not buy '{short_target}' until the baseline and failure cases are explicit.",
            "engineer": "And the hidden experiment is probably data access, not the model itself.",
            "statistician": "Define the endpoint first; otherwise the evaluation will drift.",
            "curious_peer": "Maybe split prediction, planning, and feedback into separate hypotheses.",
        }
        return templates.get(persona.id, "Yes, and I would turn that into a testable claim before adding more scope.")
    if council.id == "product":
        templates = {
            "product_thinker": "Agree. One user segment and one workflow before the big vision.",
            "ux_friend": "I would watch where the user hesitates; that is where the product truth is.",
            "skeptical_engineer": "That still needs a smaller build. Prove the core loop first.",
            "early_user": "If I cannot feel the benefit in five minutes, I probably bounce.",
            "business_realist": "Good, but retention is the honest test after the first try.",
        }
        return templates.get(persona.id, "Agree. The product version needs one user, one workflow, and one success signal.")
    if council.id == "study":
        templates = {
            "tutor": "Good point. I would explain that with one tiny example first.",
            "example_maker": f"Use '{short_target}' as the example and make it concrete.",
            "quizzer": "Then ask one check question so the gap becomes visible.",
            "misconception_checker": "Careful: that is exactly where people mix up mechanism and outcome.",
            "note_taker": "I would write that as definition, example, test, then caveat.",
        }
        return templates.get(persona.id, "Good point. I would turn it into a small example and then check understanding.")
    if council.id == "harsh_review":
        templates = {
            "reviewer_2": f"'{short_target}' is still vague. Make it falsifiable.",
            "skeptical_engineer": "If the test needs ideal conditions, it is not a test yet.",
            "practical_realist": "Stop broadening it. Pick the next action and the failure signal.",
            "evidence_checker": "Name the evidence standard before defending the idea.",
            "concise_summarizer": "Smaller claim, faster test, clearer failure. That is the move.",
        }
        return templates.get(persona.id, "Right. Useful critique means a smaller claim and a test that can actually fail.")
    return "Agree, but the next step should be more specific."


def _fallback_summary(council: Council, post_content: str, comments: list[dict[str, Any]]) -> str:
    topic = _keyword(post_content)
    first_points = [_clean_content(comment.get("content"), 120) for comment in comments[:2]]
    points = [point for point in first_points if point]
    if not points:
        points = [f"The council discussed {topic} from the perspective of {council.name}."]

    lines = ["Key points:"]
    lines.extend(f"- {point}" for point in points[:3])
    lines.append(f"- The discussion centered on making {topic} more concrete.")
    lines.append("")
    lines.append("Open questions:")
    lines.append("- What assumption should be tested first?")
    lines.append("- What evidence would change the direction?")
    lines.append("")
    lines.append("Next step:")
    lines.append("- Pick one small test and write down the success and failure signals.")
    return "\n".join(lines)[:MAX_SUMMARY_CHARS].rstrip()


def _fallback_memory(persona: Persona, council: Council, post_content: str, discussion_summary: str) -> str:
    topic = _keyword(post_content)
    addition = (
        f"The user recently discussed {topic} with the {council.name}; useful responses should stay concise, "
        "practical, and grounded in clear assumptions."
    )
    existing = persona.memory.strip()
    combined = existing if addition in existing else f"{existing} {addition}".strip()
    sentences: list[str] = []
    seen: set[str] = set()
    for sentence in re.split(r"(?<=[.!?])\s+", combined):
        cleaned = sentence.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            sentences.append(cleaned)
    combined = " ".join(sentences)
    return combined[-MAX_MEMORY_CHARS:].strip()
