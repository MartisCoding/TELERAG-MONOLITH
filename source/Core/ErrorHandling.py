import asyncio
from socket import socket
from typing import Optional, Dict
import sys

from source.Core.Logging import Logger, aprint_err

class CoreException(Exception):
    logger_obj: Optional[Logger] = None
    @classmethod
    def get_logger(cls):
        if cls.logger_obj is None:
            return
        return cls.logger_obj

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
        self.logger = self.get_logger()
        if self.logger:
            asyncio.create_task(self.log_exception())

    async def log_exception(self):
        try:
            if self.fatal:
                await self.logger.fatal(self.msg_string)
            else:
                await self.logger.exception(self.msg_string)
        except Exception as e:
            await aprint_err(f"Something went wrong while logging exception: {e}")




