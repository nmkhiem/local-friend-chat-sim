from __future__ import annotations

from pydantic import BaseModel, Field


class PostCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class PersonaOut(BaseModel):
    id: str
    name: str
    personality: str
    interests: str
    speech_style: str


class CommentOut(BaseModel):
    id: int
    post_id: int
    author_persona_id: str
    author_name: str
    parent_comment_id: int | None
    content: str
    created_at: str
    replies: list["CommentOut"] = Field(default_factory=list)


class PostOut(BaseModel):
    id: int
    content: str
    topic_summary: str
    created_at: str


class PostDetail(PostOut):
    comments: list[CommentOut]
