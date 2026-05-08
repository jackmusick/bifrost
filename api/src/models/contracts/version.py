"""Version endpoint contracts."""

from pydantic import BaseModel


class VersionResponse(BaseModel):
    version: str
