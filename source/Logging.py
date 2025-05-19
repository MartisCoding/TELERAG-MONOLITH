import asyncio, threading, time, aiofiles
import dataclasses
import enum
import os
import random
from typing import Optional, List, Coroutine
from types import MappingProxyType

class Level(enum.Enum):
    """
    Enum for logging levels.
    """
    NOTSET = 0
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50

level_to_str = MappingProxyType({
    Level.DEBUG: "DEBUG",
    Level.INFO: "INFO",
    Level.WARNING: "WARNING",
    Level.ERROR: "ERROR",
    Level.CRITICAL: "CRITICAL"
})

str_to_level = MappingProxyType({
    "DEBUG": Level.DEBUG,
    "INFO": Level.INFO,
    "WARNING": Level.WARNING,
    "ERROR": Level.ERROR,
    "CRITICAL": Level.CRITICAL
})

size_to_coefficient = MappingProxyType({
    "byte": 1,
    "bytes": 1,
    "b": 1,
    "kilobyte": 1024,
    "kilobytes": 1024,
    "kb": 1024,
    "megabyte": 1024**2,
    "megabytes": 1024**2,
    "mb": 1024**2,
})

time_to_coefficient = MappingProxyType({
    "second": 1,
    "seconds": 1,
    "sec": 1,
    "s": 1,
    "minute": 60,
    "minutes": 60,
    "min": 60,
    "m": 60,
    "hour": 3600,
    "hours": 3600,
    "h": 3600,
    "day": 86400,
    "days": 86400,
    "d": 86400,
})



@dataclasses.dataclass
class Log:
    """
    A log entry.
    """
    name: str
    level: Level
    message: str
    timestamp: int = int(time.time())

    def __str__(self):
        return f"[{self.name} / {level_to_str[self.level]}]: {self.message} - ({self.timestamp})"

class Logger:
    def __init__(self, name: str, level: Optional[Level] = None, file_gateway: "FileGateway" = None):
        self.level = level if level else Level.NOTSET
        self.gateway = file_gateway
        self._started = threading.Event()
        self.name = name

        self._entry_queue: Optional[asyncio.Queue] = None
        self._this_loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

        self._task = None

    def start(self):
        """
        Start the logger.
        """
        def runner():
            self._this_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._this_loop)
            self._entry_queue = asyncio.Queue()
            self._task = self._this_loop.create_task(self._process_queue())
            self._started.set()
            self._this_loop.run_forever()
            self._this_loop.close()

        self._thread = threading.Thread(
            target=runner,
            name=f"Logger-{self.name}{random.randint(0, 10000)}",
            daemon=True
        )
        self._thread.start()
        self._started.wait()
        self._started.clear()


    def stop(self):
        """
        Stop the logger.
        """
        asyncio.run_coroutine_threadsafe(self._entry_queue.join(), self._this_loop).result()
        asyncio.run_coroutine_threadsafe(self._entry_queue.put(None), self._this_loop).result()

        asyncio.run_coroutine_threadsafe(self._close(self._task), self._this_loop).result()
        self._this_loop.call_soon_threadsafe(self._this_loop.stop)
        self._thread.join()
        self._this_loop.close()

    @staticmethod
    async def _close(task):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def _submit_task(self, coro: Coroutine):
        """
        Submit a task to the logger's event loop.
        """
        if self._this_loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, self._this_loop)
        else:
            raise RuntimeError("Logger is not running")

    def _enqueue(self, log_entry: Log):
        """
        Enqueue a log entry to the logger's queue.
        """
        return self._submit_task(self._entry_queue.put(log_entry))

    def _log(self, level: Level, message: str):
        if self.level.value > level.value:
            return
        log_entry = Log(
            name=self.name,
            level=level,
            message=message,
        )
        self._enqueue(log_entry)

    def debug(self, message: str):
        """
        Log a debug message.
        """
        self._log(Level.DEBUG, message)

    def info(self, message: str):
        """
        Log an info message.
        """
        self._log(Level.INFO, message)

    def warning(self, message: str):
        """
        Log a warning message.
        """
        self._log(Level.WARNING, message)

    def error(self, message: str):
        """
        Log an error message.
        """
        self._log(Level.ERROR, message)

    def critical(self, message: str):
        """
        Log a critical message.
        """
        self._log(Level.CRITICAL, message)

    async def _process_queue(self):
        while True:
            log_entry = await self._entry_queue.get()
            if log_entry is None:
                break
            if self.gateway:
                self.gateway.write(str(log_entry))
            self._entry_queue.task_done()


class GateWayStrategy:
    def __init__(
            self,
            directory: Optional[str] = None,
            ext: Optional[str] = None,
            size_threshold: Optional[str] = None,
            age_threshold: Optional[str] = None,
            encoding: Optional[str] = None,
    ):
        # Check if directory exists and if not, make one. Note that path provided is not absolute but relational
        if directory is not None:
            if not os.path.exists(directory):
                os.makedirs(directory)
            if not directory[-1] == "/":
                directory += "/"
            self.directory = directory
        else:
            self.directory = None

        self.ext = ext or '.txt'

        if age_threshold is not None:
            self.age_threshold = age_threshold
            self.age_based = True
        else:
            self.age_threshold = None
            self.age_based = False

        if size_threshold is not None:
            self.size_threshold = size_threshold
            self.rotation_based = True
        else:
            self.size_threshold = None
            self.rotation_based = False

        self.encoding = encoding

    def apply(self, gateway: "FileGateway"):
        if self.directory:
            gateway.set_base_logs_location(self.directory)
        if self.ext:
            gateway.set_base_logs_ext(self.ext)
        if self.encoding:
            gateway.set_encoding(self.encoding)

        if self.rotation_based:
            gateway.set_rotation_based(self.rotation_based)
            if isinstance(self.size_threshold, int):
                gateway.set_rotation_threshold(self.size_threshold)
            elif isinstance(self.size_threshold, str):
                gateway.set_rotation_threshold(self.__from_size_threshold(self.size_threshold))
            else:
                raise ValueError(f"Invalid size threshold: {self.size_threshold}")

        if self.age_based:
            gateway.set_age_based(self.age_based)
            if isinstance(self.age_threshold, int):
                gateway.set_retention_threshold(self.age_threshold)
            elif isinstance(self.age_threshold, str):
                gateway.set_retention_threshold(self.__from_age_threshold(self.age_threshold))
            else:
                raise ValueError(f"Invalid age threshold: {self.age_threshold}")




    @staticmethod
    def __from_size_threshold(threshold: str):
        """
        Create an integer representation of bytes from a string.
        """
        two_str = threshold.split(" ")
        if len(two_str) == 1 and two_str[0].isdigit():
            return int(two_str[0])
        elif len(two_str) == 2 and two_str[0].isdigit():
            return int(two_str[0]) * size_to_coefficient.get(two_str[1].lower(), 1)
        else:
            raise ValueError(f"Invalid size threshold: {threshold}")

    @staticmethod
    def __from_age_threshold(threshold: str):
        """
        Create an integer representation of seconds from a string.
        """
        two_str = threshold.split(" ")
        if len(two_str) == 1 and two_str[0].isdigit():
            return int(two_str[0])
        elif len(two_str) == 2 and two_str[0].isdigit():
            return int(two_str[0]) * time_to_coefficient.get(two_str[1].lower(), 1)
        else:
            raise ValueError(f"Invalid age threshold: {threshold}")

class FileGateway:
    def __init__(self, file_name: str, encoding: str = "utf-8"):
        self.destination = file_name
        self._encoding = encoding
        self._base_logs_location = "./logs/"
        self._base_logs_ext = ".log"
        self._rotation_based = False
        self._retention_based = False
        self._rotation_threshold = 0
        self._retention_threshold = 0
        self._rotated_lock = threading.Lock()
        self.rotated = []
        self._path_lock = threading.Lock()# Keeps old file names for further deletion upon age based rotation
        self.full_path = f"{self._base_logs_location}{int(time.time())}-{self.destination}{self._base_logs_ext}"
        self._entry_queue: Optional[asyncio.Queue] = None
        self._thread: Optional[threading.Thread] = None
        self._retention_thread: Optional[threading.Thread] = None
        self._this_thread_loop: Optional[asyncio.AbstractEventLoop] = None
        self._this_retention_loop: Optional[asyncio.AbstractEventLoop] = None
        self._started_thread = threading.Event()
        self._started_retention_thread = threading.Event()
        self._stop_event = threading.Event()
        self._thread_task = None
        self._ret_task = None
        self.ready_to_be_deleted = False


    def get_destination(self):
        return self.destination

    def __repr__(self):
        return (f'FileGateway(\n'
                f'  location={self.destination},\n'
                f'  encoding={self._encoding},\n'
                f'  base_logs_location={self._base_logs_location},\n'
                f'  base_logs_ext={self._base_logs_ext},\n'
                f'  rotation_based={self._rotation_based},\n'
                f'  retention_based={self._retention_based},\n'
                f'  rotation_threshold={self._rotation_threshold},\n'
                f'  retention_threshold={self._retention_threshold},\n'
                f'  rotated={self.rotated},\n'
                f'  full_path={self.full_path}\n'
                f')')

    def set_age_based(self, age_based: bool):
        self._retention_based = age_based

    def set_rotation_based(self, rotation_based: bool):
        self._rotation_based = rotation_based

    def set_rotation_threshold(self, threshold: int):
        self._rotation_threshold = threshold

    def set_retention_threshold(self, threshold: int):
        self._retention_threshold = threshold
    def set_encoding(self, encoding: str):
        self._encoding = encoding

    def set_base_logs_location(self, location: str):
        self._base_logs_location = location

    def set_base_logs_ext(self, ext: str):
        self._base_logs_ext = ext

    async def _process_queue(self):
        while True:
            log_entry = await self._entry_queue.get()
            if log_entry is None:
                self._stop_event.set()
                break
            with self._rotated_lock:
                async with aiofiles.open(self.full_path, mode="a", encoding=self._encoding) as file:
                    await file.write(log_entry + "\n")
                    await file.flush()

            self._entry_queue.task_done()

    async def _process_retention(self):
        if not self._retention_based:
            return
        while True:
            if self._started_thread.is_set() or not self._retention_based:
                break
            await asyncio.sleep(10)
            self.__if_delete()

    def __if_rotate(self):
        """
        Check if the file should be rotated based on the size threshold.
        """
        if self._rotation_based:
            file_size = os.path.getsize(self.full_path)
            if file_size >= self._rotation_threshold:
                with self._rotated_lock:
                    self.rotated.append(self.full_path)
                with self._path_lock:
                    new_file_name = f"{self._base_logs_location}{int(time.time())}-{self.destination}{self._base_logs_ext}"
                    self.full_path = new_file_name

    def __if_delete(self):
        """
        Check if the file should be deleted based on the age threshold.
        """
        if self._retention_based:
            current_time = time.time()
            with self._rotated_lock:
                for file in self.rotated:
                    if current_time - os.path.getmtime(file) >= self._retention_threshold:
                        os.remove(file)
                        self.rotated.remove(file)

    def start(self):
        """
        Start the file gateway.
        """
        def thread_runner():
            self._this_thread_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._this_thread_loop)
            self._entry_queue = asyncio.Queue()
            self._thread_task = self._this_thread_loop.create_task(self._process_queue())
            self._started_thread.set()
            self._this_thread_loop.run_forever()
            self._this_thread_loop.close()
        def retention_runner():
            self._this_retention_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._this_retention_loop)
            self._ret_task = self._this_retention_loop.create_task(self._process_retention())
            self._started_retention_thread.set()
            self._this_retention_loop.run_forever()
            self._this_retention_loop.close()

        self._thread = threading.Thread(
            name=f"FileGateway-{self.destination}{random.randint(0, 10000)}",
            target=thread_runner
        )
        self._retention_thread = threading.Thread(
            name=f"FileGateway-RetSolver-{self.destination}{random.randint(0, 10000)}",
            target=retention_runner
        )
        self._thread.start()
        self._retention_thread.start()
        self._started_thread.wait()
        self._started_thread.clear()

    def _submit_task(self, coro: Coroutine):
        """
        Submit a task to the file gateway's event loop.
        """
        if self._this_thread_loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, self._this_thread_loop)
        else:
            raise RuntimeError("File gateway is not running")

    def _enqueue(self, message: str):
        if not self._this_thread_loop or not self._this_retention_loop or not self._entry_queue:
            raise RuntimeError("File gateway is not running. Therefore, Queue was not initialized.")
        return self._submit_task(self._entry_queue.put(message))

    def stop(self):
        """
        Stop the file gateway.
        """
        if self.ready_to_be_deleted:
            return

        asyncio.run_coroutine_threadsafe(self._entry_queue.join(), self._this_thread_loop).result()
        asyncio.run_coroutine_threadsafe(self._entry_queue.put(None), self._this_thread_loop).result()
        self._entry_queue = None

        asyncio.run_coroutine_threadsafe(self._close(self._thread_task), self._this_thread_loop).result()

        self._this_thread_loop.call_soon_threadsafe(self._this_thread_loop.stop)
        self._thread.join()
        self._this_thread_loop.close()

        asyncio.run_coroutine_threadsafe(self._close(self._ret_task), self._this_retention_loop).result()
        self._this_retention_loop.call_soon_threadsafe(self._this_retention_loop.stop)
        self._retention_thread.join()
        self._this_retention_loop.close()
        self.ready_to_be_deleted = True

    @staticmethod
    async def _close_queue(queue: asyncio.Queue):
        """
        Close the queue.
        """
        await queue.join()
        await queue.put(None)
        await queue.join()


    @staticmethod
    async def _close(task):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


    def write(self, message: str):
        """
        Write a message to the file gateway.
        """
        if not self._this_thread_loop or not self._this_retention_loop:
            raise RuntimeError("File gateway is not running.")
        self._enqueue(message)

@dataclasses.dataclass
class LoggerModel:
    logger_name: str
    logger_obj: Logger
    file_gateway: FileGateway
    file_gateway_destination: str

class LoggerRegistry:
    """
    A registry for loggers to ensure that each logger is only created once.
    """
    _instance: Optional["LoggerRegistry"] = None
    @classmethod
    def get_instance(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = LoggerRegistry(*args, **kwargs)
        return cls._instance

    @classmethod
    def set_instance(cls, instance: "LoggerRegistry"):
        if cls._instance is not None:
            raise RuntimeError("LoggerRegistry instance already set.")
        cls._instance = instance

    def __init__(self, level: str = "INFO", gateway_strategy: GateWayStrategy = None):
        self.level = str_to_level.get(level.upper(), Level.INFO)
        self._loggers: List[LoggerModel] = []
        self.strategy = gateway_strategy
        LoggerRegistry.set_instance(self)


    def get_or_create(self, name: str, destination: str) -> Logger:
        """
        Get or create a logger with the given name and destination.
        :param name:
        :param destination:
        :return:
        """
        matching_gateways = None
        for logger in self._loggers:
            if logger.file_gateway_destination == destination:
                matching_gateways = logger.file_gateway
            if logger.logger_name == name and logger.file_gateway_destination == destination:
                return logger.logger_obj
        if matching_gateways is None:
            file_gateway = FileGateway(destination)
            file_gateway.start()
            if self.strategy:
                self.strategy.apply(file_gateway)
        else:
            file_gateway = matching_gateways
        logger = Logger(name, self.level, file_gateway)
        logger.start()
        self._loggers.append(LoggerModel(name, logger, file_gateway, file_gateway.get_destination()))
        return logger

    def remove_one(self, name: str, destination) -> bool:
        for logger in self._loggers:
            if logger.logger_name == name and logger.file_gateway_destination == destination:
                logger.logger_obj.stop()
                logger.file_gateway.stop()
                self._loggers.remove(logger)
                return True
        return False

    def stop_all(self):
        """
        Stop all loggers and file gateways.
        """
        for logger in self._loggers:
            logger.logger_obj.stop()
            logger.file_gateway.stop()
        self._loggers = []



def get_logger(name: str, destination: str) -> Logger:
    """
    Get a logger with the given name and destination.
    :param name:
    :param destination:
    :return:
    """
    registry = LoggerRegistry.get_instance()
    return registry.get_or_create(name, destination)
