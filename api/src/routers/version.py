from fastapi import APIRouter
from pydantic import BaseModel

from shared.version import MIN_CLI_VERSION, get_version

router = APIRouter(prefix="/api/version", tags=["version"])


class VersionResponse(BaseModel):
    version: str
    min_cli_version: str


@router.get("", response_model=VersionResponse)
async def get_version_info() -> VersionResponse:
    return VersionResponse(
        version=get_version(),
        min_cli_version=MIN_CLI_VERSION,
    )
