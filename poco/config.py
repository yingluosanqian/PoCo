from __future__ import annotations

from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = getenv("POCO_APP_NAME", "PoCo")
