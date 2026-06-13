from __future__ import annotations

from pydantic import BaseModel, Field


class PostCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    council_id: str | None = Field(default=None, max_length=120)


class ModelSelect(BaseModel):
    model: str | None = Field(default=None, min_length=1, max_length=120)
    provider: str | None = Field(default=None, min_length=1, max_length=40)


class PersonaOut(BaseModel):
    id: str
    name: str
    avatar_label: str
    personality: str
    interests: str
    speech_style: str
    role: str
    is_active: bool
    memory: str = ""
    created_at: str
    updated_at: str


class PersonaUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    avatar_label: str | None = Field(default=None, min_length=1, max_length=8)
    personality: str | None = Field(default=None, min_length=1, max_length=1200)
    interests: str | None = Field(default=None, min_length=1, max_length=1200)
    speech_style: str | None = Field(default=None, min_length=1, max_length=1200)
    role: str | None = Field(default=None, min_length=1, max_length=240)
    is_active: bool | None = None


class PersonaMemoryIn(BaseModel):
    memory: str = Field(default="", max_length=1200)


class PersonaMemoryOut(BaseModel):
    persona_id: str
    memory: str
    updated_at: str


class CouncilOut(BaseModel):
    id: str
    name: str
    description: str
    simulation_style: str
    persona_ids: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class CouncilDetail(CouncilOut):
    personas: list[PersonaOut] = Field(default_factory=list)


class CouncilUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, min_length=1, max_length=1600)
    simulation_style: str | None = Field(default=None, min_length=1, max_length=1600)
    persona_ids: list[str] | None = None


class CommentOut(BaseModel):
    id: int
    post_id: int
    author_persona_id: str
    author_name: str
    author_avatar_label: str = ""
    parent_comment_id: int | None
    content: str
    created_at: str
    replies: list["CommentOut"] = Field(default_factory=list)


class PostOut(BaseModel):
    id: int
    content: str
    topic_summary: str
    council_id: str
    council_name: str = ""
    discussion_summary: str = ""
    model: str = ""
    comment_count: int = 0
    created_at: str


class PostDetail(PostOut):
    council: CouncilDetail | None = None
    comments: list[CommentOut]
