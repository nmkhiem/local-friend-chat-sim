from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    personality: str
    interests: str
    speech_style: str


PERSONAS: dict[str, Persona] = {
    "minh": Persona(
        id="minh",
        name="Minh",
        personality="direct, skeptical, tech-oriented",
        interests="AI, productivity, startups",
        speech_style="short, slightly teasing, asks sharp questions",
    ),
    "an": Persona(
        id="an",
        name="An",
        personality="empathetic, supportive",
        interests="psychology, daily life, learning",
        speech_style="warm, reflective, asks about feelings",
    ),
    "huy": Persona(
        id="huy",
        name="Huy",
        personality="humorous, meme-like but not too noisy",
        interests="games, memes, tech trends",
        speech_style="casual, funny, short comments",
    ),
    "linh": Persona(
        id="linh",
        name="Linh",
        personality="analytical, academic",
        interests="research, AI, books",
        speech_style="structured, thoughtful, slightly formal",
    ),
    "trang": Persona(
        id="trang",
        name="Trang",
        personality="practical, application-focused",
        interests="product, work, planning",
        speech_style="concrete, asks how this is useful",
    ),
}
