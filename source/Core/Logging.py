import asyncio
import enum
import sys

import aiofiles
from datetime import datetime
from typing import Optional

from source.Core.DependencyInjection import Injectable
from source.Core.ErrorHandling import CoreException

class LoggingCreationException(CoreException):
    destination = "default"
class LoggingCancellation(CoreException):
    destination = "default"

class BaseLogger:

    async def exception(self, message):
        raise NotImplementedError(
            "Up to subclasses to implement this method."
        )




class LoggerComposer(Injectable):
    """
    A class that helps create, manage and use loggers.
    """
    _instance: Optional["LoggerComposer"] = None

    @classmethod
    def set_instance(cls, instance: "LoggerComposer"):
        """
        Set the instance of the composer.
        """
        if cls._instance is not None:
            raise RuntimeError(
                "LoggerComposer instance already set. Use get_instance() to access it."
            )
        cls._instance = instance

    @classmethod
    def get_instance(cls) -> "LoggerComposer":
        """
        Get the instance of the composer.
        """
        if cls._instance is None:
            raise RuntimeError(
                "LoggerComposer instance not set. To create it, create instance of Logger class. It will create composer instance for automatically."
            )
        return cls._instance

    dependencies = []
    is_dependency = True
    resolved = True

    def __init__(self):
        self._loggers = {}

    def get_logger(self, name: str) -> BaseLogger:
        """
        Get a logger by name.
        """
        if name not in self._loggers:
            raise ValueError(f"Logger {name} not found.")
        return self._loggers[name][0]

    def add_logger(self, name: str, logger: BaseLogger, file_location: str):
        """
        Add a logger to the composer.
        """
        if name in self._loggers:
            raise ValueError(f"Logger {name} already exists.")
        self._loggers[name] = (logger, file_location)

    def remove_logger(self, name: str):
        """
        Remove a logger from the composer. Proceed with caution. It may break essential deps in your app.
        """
        if name not in self._loggers:
            raise ValueError(f"Logger {name} not found.")
        del self._loggers[name]

    def get_all(self):
        """
        Get all loggers.
        """
        return self._loggers

    def verify_file_location(self, file: str) -> bool:
        """
        it checks for any matches of logfile location in the list of loggers. If it finds any, it returns False. Because each logger must have unique file location.
        """
        for logger in self._loggers.values():
            if logger[1] == file:
                return False
        return True


class ComposerMeta(type):
    """
    A metaclass that helps to register Logger classes to a compositor counterpart automatically, and to ensure that composer remains singleton.
    """
    _instance: Optional[LoggerComposer] = None
    @classmethod
    def _get_composer(cls) -> LoggerComposer:
        """get composer instance"""
        if cls._instance is None:
            try:
                composer = LoggerComposer.get_instance()
                return composer
            except RuntimeError:
                composer = LoggerComposer()
                LoggerComposer.set_instance(composer)
                cls._instance = composer
        return cls._instance

    def __new__(cls, name, bases, dct):
        composer = cls._get_composer()
        if issubclass(cls, BaseLogger):
            # Register the logger class to the composer
            instance = super().__new__(cls, name, bases, dct)
            logger_name = dct.get("name")
            logfile_location = dct.get("file")

            if not composer.verify_file_location(logfile_location):
                raise LoggingCreationException(
                    where="ComposerMeta.__new__",
                    what="Could not register logger class to composer",
                    summary="Logger file location already exists. Please provide unique file location. DO NOT USE SAME FILE LOCATION FOR MULTIPLE LOGGERS.",
                )

            if not logger_name:
                logger_name = "default"
                try:
                    composer.add_logger(logger_name, instance, logfile_location)
                except ValueError:
                    raise LoggingCreationException(
                        where="ComposerMeta.__new__, while registering logger class to composer",
                        what="Could not register logger class to composer",
                        summary="Could not gather logger name from class. Tried name it 'default', however this name was already been used by another logger class instance.",
                        full_message="Could not register logger class to composer."
                        "Tried to name it 'default', however this name was already been used by another logger class instance."
                        "Please, provide a unique name for your logger class. Your instance must provide name attribute in class body, or in __init__ method.",
                        fatal=False,
                    )
                finally:
                    return composer.get_logger('default')
            else:
                try:
                    composer.add_logger(logger_name, instance, logfile_location)
                except ValueError:
                    raise LoggingCreationException(
                        where="ComposerMeta.__new__, while registering logger class to composer",
                        what="Could not register logger class to composer",
                        summary="Could not register logger class to composer. Logger name already exists.",
                        full_message="Could not register logger class to composer. Logger name already exists."
                                     "Please provide unique name in your class instance.",
                        fatal=False
                    )
                finally:
                    return composer.get_logger('default')
        else:
            raise LoggingCreationException(where="ComposerMeta.__new__", what="Could not register logger class to composer", summary="Class is not a subclass of BaseLogger", fatal=False)


class LogLevel(enum.Enum):
    SIGSTOP = -1
    DEBUG = 0
    INFO = 1
    WARNING = 2
    ERROR = 3
    FATAL = 4
    EXCEPTION = 5
    QUIET = 6
    NOTSET = 7


class Logger(BaseLogger, metaclass=ComposerMeta):
    """
    This is a logger class. It logs messages to the log file. Pretty much nothing to explain. Logger is logger, not a rocket.
    """
    def __init__(self, name: str = "default", file: str = "log.txt"):
        """
        Initialize the logger.
        """
        self.name = name
        self._file_location = file
        self._level = LogLevel.NOTSET
        self._max_buffer_size = 100
        self._buffer = ""
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._queue_processing_task: Optional[asyncio.Task] = None
        self._logging = True

    def create(self):
        """
        Create the logger. It creates the log file and starts the logging loop.
        """
        if self._queue_processing_task is not None:
            raise LoggingCreationException(
                where=f"Logger({self.name}).create",
                what="Logger already created",
                summary="Do not try to create logger twice. It will not work. You will get an exception. Shtupid",
                fatal=False,
            )
        self._queue_processing_task = asyncio.create_task(self._process_queue())
        self._logging = True

    async def log(self, loglevel: LogLevel, message: str):
        """
        Log a message to the log file.
        """
        int_level = loglevel.value
        int_self_level = self._level.value
        if self._level == LogLevel.QUIET:
            return
        if loglevel == LogLevel.SIGSTOP:
            await self._message_queue.put(None)
            return
        if int_level >= int_self_level:
            await self._message_queue.put((loglevel, message))

        if self._queue_processing_task is None:
            self.create()


    def _apply_decorations(self, level: LogLevel,  message: str) -> str:
        """
        Apply decorations to the message.
        """
        if level == LogLevel.DEBUG:
            level_string = "DEBUG"
        elif level == LogLevel.INFO:
            level_string = "INFO"
        elif level == LogLevel.WARNING:
            level_string = "WARNING"
        elif level == LogLevel.ERROR:
            level_string = "ERROR"
        elif level == LogLevel.FATAL:
            level_string = "FATAL"
        elif level == LogLevel.EXCEPTION:
            level_string = "EXCEPTION"
        else:
            level_string = "NOTSET"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"[{timestamp} - {self.name}/{level_string}] -> {message}"

    async def _process_queue(self):
        while self._logging:
            try:
                msg = await self._message_queue.get()
                if msg is None:
                    raise LoggingCancellation(
                        where=f"Logger({self.name})._process_queue",
                        what=f"Logger {self.name} was stopped",
                        summary="",
                        fatal=False,
                    )
                loglevel, message = msg
                message = self._apply_decorations(loglevel ,message)
                self._buffer += message + "\n"
                if len(self._buffer) >= self._max_buffer_size:
                    await self._flush_buffer()
                    await asyncio.sleep(0.01)
            except (asyncio.CancelledError, LoggingCancellation):
                break
            except Exception as e:
                raise LoggingCancellation(
                    where=f"Logger({self.name})._process_queue",
                    what="Error while processing queue",
                    summary="",
                    full_message=str(e),
                    fatal=False,
                )

    async def _flush_buffer(self):
        """
        Flush the buffer to the log file.
        """
        if self._buffer:
            try:
                async with aiofiles.open(self._file_location, "a") as f:
                        await f.write(self._buffer)
            except OSError as e:
                await self.log(LogLevel.ERROR, f"Error while writing to log file: {e}. Probably file is not accessible. The buffer will be printed instead.")
                await self.print_buf()
            except Exception as e:
                await self.log(LogLevel.ERROR, f"Unexpected while writing to log file: {e}. The buffer will be printed instead.")
                await self.print_buf()
            finally:
                self._buffer = ""
                await asyncio.sleep(0.01)

    async def print_buf(self):
        """
        Print the buffer and flush.
        """
        await asyncio.to_thread(sys.stdout.write, self._buffer.encode("utf-8"))
        await self._flush_buffer()

    async def get(self, last: int = 10):
        """
        Get the last n lines from the log file.
        """
        lines = self._buffer.split("\n")
        if len(lines) <= last:
            return lines
        return lines[-last:]









