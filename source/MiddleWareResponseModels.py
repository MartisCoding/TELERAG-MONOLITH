import threading
from typing import Optional, Callable, Any, Awaitable, List, Dict
import asyncio


class BaseResponseModel:
    def __init__(self):
        self._next: Optional[Callable[["BaseResponseModel"], Optional[Any]], Awaitable["BaseResponseModel"], Optional[Any]] = None
        self._got_result = threading.Event()
        self._got_result_async = asyncio.Event()
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = asyncio.get_event_loop()
        self._result = None

    @property
    def next_task(self):
        return self._next

    def set_next(self, next_middleware: Callable):
        self._next = next_middleware

    def result(self) -> Any:
        self._got_result.wait()
        if isinstance(self._result, Exception):
            raise self._result
        return self._result

    async def result_async(self) -> Any:
        await self._got_result_async.wait()
        if isinstance(self._result, Exception):
            raise self._result
        return self._result

    def put_result(self, result: Any):
        if self._next is None or isinstance(result, Exception):
            self._result = result
            self._got_result.set()
            self._loop.call_soon_threadsafe(self._got_result_async.set)


class RetrievalAugmentedResponse(BaseResponseModel):
    def __init__(self, query: Optional[str] = None, channel_names: Optional[List[str]] = None, user_name: Optional[str] = None):
        super().__init__()
        self.user_name = user_name
        self.query: Optional[str] = query
        self.channel_names: Optional[List[str]] = channel_names
        self.sources = None
        self.channels_and_messages: Dict[str, List[str]] = {}
        self.chroma_response: Optional[List[Dict[str, Any]]] = None
