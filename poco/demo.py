from __future__ import annotations

from pydantic import BaseModel, Field


class DemoCommandRequest(BaseModel):
    text: str = Field(..., min_length=1, description="A PoCo command such as /run <prompt>.")
    user_id: str = Field(default="local_demo_user", description="Synthetic requester id for local demo use.")

