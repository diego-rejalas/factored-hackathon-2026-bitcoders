"""Response models. The agent's tools are typed against these, so they are the contract."""
from datetime import datetime

from pydantic import BaseModel


class Health(BaseModel):
    status: str


class TableCount(BaseModel):
    table: str
    rows: int


class LastRun(BaseModel):
    run_id: str
    status: str
    started_at: datetime
    finished_at: datetime


class DataMeta(BaseModel):
    """What the gold layer holds and when the pipeline last succeeded."""

    gold: list[TableCount]
    last_successful_run: LastRun | None
