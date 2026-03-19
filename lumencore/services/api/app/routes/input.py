from __future__ import annotations

import logging

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from ..commands.command_runtime import execute_command_request
from ..schemas.commands import CommandRunRequest, CommandRunResponse

router = APIRouter(prefix="/api/input", tags=["input"])
logger = logging.getLogger(__name__)


class InputCommandRequest(BaseModel):
    input_text: str = Field(min_length=1, max_length=500)


@router.post("/command", response_model=CommandRunResponse, status_code=status.HTTP_202_ACCEPTED)
def input_command(req: InputCommandRequest) -> CommandRunResponse:
    logger.info("External input ingress received via /api/input/command")
    return execute_command_request(
        CommandRunRequest(
            command_text=req.input_text,
            tenant_id="owner",
            project_id="default",
        ),
        None,
        None,
    )
