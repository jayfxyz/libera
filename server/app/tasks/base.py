"""Task definitions: what a task is, and what a handler is given."""

from dataclasses import dataclass
from typing import ClassVar, Generic, TypeVar

from pydantic import BaseModel

P = TypeVar("P", bound=BaseModel)


class BaseTask(BaseModel, Generic[P]):
    """A kind of work. Subclass with a payload model and a `name`:

        class DownloadBook(BaseTask[DownloadBookPayload]):
            name = "download_book"
    """

    name: ClassVar[str]
    max_attempts: ClassVar[int] = 1
    payload: P


class TaskFailed(Exception):
    """Raised by a handler to fail its task. Permanent unless retry=True
    (and then only while attempts remain). Any other exception retries."""

    def __init__(self, message: str, retry: bool = False):
        super().__init__(message)
        self.retry = retry


class TaskDeferred(Exception):
    """Raised by a handler to put its task back for later, without using up an
    attempt: the task couldn't run yet (e.g. the service asked us to slow down)."""

    def __init__(self, message: str, delay: float):
        super().__init__(message)
        self.delay = delay  # seconds before the task may run again


@dataclass(frozen=True)
class TaskContext:
    task_id: str
    attempt: int  # 1 on the first run
    max_attempts: int
