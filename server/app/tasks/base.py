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


@dataclass(frozen=True)
class TaskContext:
    task_id: str
    attempt: int  # 1 on the first run
    max_attempts: int
