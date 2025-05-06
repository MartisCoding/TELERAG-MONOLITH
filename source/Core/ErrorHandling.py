import asyncio
from socket import socket
from typing import Optional, Dict
import sys

from source.Core.Logging import BaseLogger

class CoreException(Exception):
    destination: str
    def __init__(
            self,
            where: str,
            what: str,
            summary: str,
            full_message: Optional[str] = None,
            fatal: bool = False
    ):
        self.msg_string = f"Exception at {where}: {what}. {'Summary ' + summary if summary else ''} \n {full_message if full_message else ''}"
        self.fatal = fatal
        super().__init__(self.msg_string)


class ErrorHandler:
    def __init__(self, **kwargs: BaseLogger):
        self.routes: Dict[str, BaseLogger] = {}
        self.loggers = kwargs
        self.dead_end = BaseLogger()
        self._build_routes()
        self._build_hook()
        self.handling = False
        self.routing_queue = asyncio.Queue()
        self._queue_processing_task = asyncio.create_task(self._process_exception_loop())

    def _build_routes(self):
        called_dead_end = 0
        for name, logger in self.loggers.items():
            if isinstance(logger, BaseLogger):
                self.routes[name] = logger
            else:
                self.routes[name] = self.dead_end
                called_dead_end += 1

        if called_dead_end == 0:
            self.dead_end = None

        if not self.routes:
            raise RuntimeError(
                "Cannot perform propper exception logging due to absense of valid loggers"
            )

        self.loggers = None

    async def _process_exception_loop(self):
        while self.handling:
            try:
                msg = await self.routing_queue.get()
                destination, message = msg
                logger = self.routes[destination]
                if logger:
                    await logger.exception(message)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print("Error in exception handling loop:", e)

    async def stop_handling(self):
        self.handling = False
        await self.routing_queue.join()
        try:
            await self._queue_processing_task
        except asyncio.CancelledError:
            pass


    def _build_hook(self):
        routes = self.routes
        queue_ref = self.routing_queue
        def core_exception_hook(exc_type, exc_value, traceback):
            if isinstance(exc_value, CoreException):
                destination = getattr(exc_value, "destination", "default")
                msg = str(exc_value)

                if destination in routes:
                    try:
                        queue_ref.put_nowait((destination, msg))
                    except asyncio.QueueFull:
                        print("Routing queue is full, dropping exception:", msg)

                if exc_value.fatal:
                    sys.__excepthook__(exc_type, exc_value, traceback)
            else:
                sys.__excepthook__(exc_type, exc_value, traceback)
        sys.excepthook = core_exception_hook


