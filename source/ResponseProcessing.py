import enum
import random
import time
from typing import Optional, List
from MiddleWareResponseModels import BaseResponseModel
from types import MappingProxyType
import asyncio, threading, queue

from Logging import TLog

state_to_str_mapping = MappingProxyType({
    0: "IDLE",
    1: "BUSY",
    2: "TERMINATED"
})

class Estate(enum.Enum):
    IDLE = 0
    BUSY = 1
    TERMINATED = 2

class Executor:
    def __init__(self, executor_id: int, max_queue_size: int = 10):
        self._bottleneck = 0
        self._max_queue_size = max_queue_size
        self._logger = TLog.get_logger(f"Executor-{executor_id}", "Runtime")
        self._executor_id = executor_id
        self._state = Estate.IDLE
        self._this_task: Optional[asyncio.Task] = None
        self._this_loop: Optional[asyncio.AbstractEventLoop] = None
        self._this_queue: Optional[asyncio.Queue[Optional[BaseResponseModel]]] = None
        self._thread: Optional[threading.Thread] = None
        self._started = threading.Event()
        self._last_task_time = int(time.time())
        self._unfreeze = threading.Event()
        self._unfreeze.set()

    @property
    def bottleneck(self):
        return self._bottleneck

    def increment_bottleneck(self):
        self._bottleneck += 1
        if self._bottleneck >= self._max_queue_size:
            self._unfreeze.clear()

    def decrement_bottleneck(self):
        if self._bottleneck > 0:
            self._bottleneck -= 1
        if self._bottleneck < self._max_queue_size:
            self._unfreeze.set()


    @property
    def state(self) -> Estate:
        return self._state

    @property
    def queue_full(self) -> bool:
        return self._this_queue is not None and self.bottleneck >= self._max_queue_size

    @property
    def queue_empty(self) -> bool:
        return self._this_queue is not None and self.bottleneck >= self._max_queue_size

    @property
    def queue_size(self) -> int:
        return self._this_queue.qsize() if self._this_queue is not None else 0

    @property
    def last_task_time(self) -> float:
        return self._last_task_time

    def start(self):
        def runner():
            self._this_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._this_loop)
            self._this_queue = asyncio.Queue()
            self._started.set()
            self._this_task = self._this_loop.create_task(self._process_response_object())
            self._this_loop.run_forever()
            self._this_loop.close()

        self._thread = threading.Thread(target=runner, name=f"Executor - {self._executor_id}")
        self._thread.start()
        self._started.wait()

    async def _process_response_object(self):
        while True:
            task = await self._this_queue.get()
            if task is None:
                break
            if self._state == Estate.IDLE:
                self._state = Estate.BUSY
            self._last_task_time = int(time.time())
            try:
                result = None
                while task.next_task is not None:
                    if asyncio.iscoroutinefunction(task.next_task):
                        result = await task.next_task(task) or None
                    else:
                        result = task.next_task(task) or None
                task.put_result(result)
            except Exception as e:
                self._logger.error(f"Error processing task {task}: {e}")
                task.put_result(e)
            finally:
                if self._this_queue.empty():
                    self._state = Estate.IDLE
                self._this_queue.task_done()
                self.decrement_bottleneck()
                await asyncio.sleep(0.1)

    def add_task(self, task: BaseResponseModel):
        self.increment_bottleneck()
        if self._this_queue is None:
            raise RuntimeError("Executor not started.")
        if not self._unfreeze.is_set():
            self._unfreeze.wait()
        asyncio.run_coroutine_threadsafe(self._this_queue.put(task), self._this_loop)

    @staticmethod
    async def _cancel_task(task):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def stop(self):
        asyncio.run_coroutine_threadsafe(self._this_queue.join(), self._this_loop).result()
        asyncio.run_coroutine_threadsafe(self._this_queue.put(None), self._this_loop).result()
        asyncio.run_coroutine_threadsafe(self._cancel_task(self._this_task), self._this_loop).result()

        if self._this_loop.is_running():
            self._this_loop.call_soon_threadsafe(self._this_loop.stop)

        self._thread.join()
        self._thread = None
        self._this_task = None
        self._this_loop = None
        self._this_queue = None
        self._state = Estate.TERMINATED

class ExecutorManager:

    _instance: Optional["ExecutorManager"] = None

    @classmethod
    def get_instance(cls) -> "ExecutorManager":
        if cls._instance is None:
            raise RuntimeError("Executor manager not initialized.")
        return cls._instance

    def __init__(self, maximum_executors: int = 10, minimum_executors: int = 2, executor_timeout: int = 60, max_queue_size: int = 10, max_self_queue_size: int = 10):
        self._max_queue_size = max_queue_size
        self._executor_timeout = executor_timeout
        self._maximum_executors = maximum_executors
        self._min_executors = minimum_executors
        self._thread_pool: List[Executor] = []
        self._logger = TLog.get_logger("ExecutorManager", "Runtime")
        self._manager_lock = threading.Lock()
        self._unlock_event = threading.Event()
        self._task_incoming_event = threading.Event()
        self._unlock_event.set()
        self._manager_thread = threading.Thread(target=self._dispatcher_thread_loop, name="ExecutorManagerThread")
        self._started = threading.Event()
        self._task_queue = queue.Queue(maxsize=max_self_queue_size)


    def push(self, task: BaseResponseModel):
        if not self._thread_pool:
            raise RuntimeError("No executors available.")
        if not self._task_incoming_event.is_set():
            self._task_incoming_event.set()
        self._task_queue.put(task)


    def _dispatch_task(self, task: BaseResponseModel) -> bool:
        snapshot = self._snapshot()
        with self._manager_lock:
            if not self._thread_pool:
                return False
            min_exec: Executor = min(self._thread_pool, key=lambda t: t.bottleneck)
            if min_exec.bottleneck >= self._max_queue_size // 2 and len(self._thread_pool) < self._maximum_executors:
                executor = Executor(len(self._thread_pool) + int(time.time()), self._max_queue_size)
                executor.start()
                self._thread_pool.append(executor)
                executor.add_task(task)
                min_exec = executor
            else:
                min_exec.add_task(task)
        if min_exec.bottleneck >= self._max_queue_size:
            self._unlock_event.clear()
            return False
        return True
    def _create_one(self):
        with self._manager_lock:
            executor = Executor(len(self._thread_pool) + int(time.time() + random.randint(0, 1000)), self._max_queue_size)
            executor.start()
            self._thread_pool.append(executor)
        return executor

    def _snapshot(self):
        snapshots = []
        with self._manager_lock:
            for executor in self._thread_pool:
                snapshots.append({
                    "executor_id": executor._executor_id,
                    "state": state_to_str_mapping[executor.state.value],
                    "queue_size": executor.queue_size,
                    "last_task_time": executor.last_task_time
                })
        return snapshots

    def _cleanup(self):
        with self._manager_lock:
            stopped = 0
            for executor in self._thread_pool:
                if int(time.time()) - executor.last_task_time > self._executor_timeout and stopped < self._maximum_executors - self._min_executors:
                    executor.stop()
                    stopped += 1
            new_pool = []
            for i in range(len(self._thread_pool)):
                if self._thread_pool[i].state != Estate.TERMINATED:
                    new_pool.append(self._thread_pool[i])
                else:
                    self._thread_pool[i] = None
            self._thread_pool = new_pool



    def _dispatcher_thread_loop(self):
        self._started.set()
        while self._started.is_set():
            if self._unlock_event.is_set():
                try:
                    task = self._task_queue.get(timeout=self._executor_timeout + 2)
                except queue.Empty:
                    self._cleanup()
                    self._task_incoming_event.clear()
                    self._task_incoming_event.wait()
                    task = self._task_queue.get()
                if task is None:
                    break
                if not self._dispatch_task(task):
                    self._logger.debug("No executor available. Stopping task dispatch and waiting until one is free.")
            else:
                with self._manager_lock:
                    for executor in self._thread_pool:
                        if not executor.queue_full:
                            self._unlock_event.set()
                            break
                time.sleep(0.1)

    def start(self):
        for _ in range(self._min_executors):
            self._create_one()
        self._manager_thread.start()
        self._started.wait()

    def stop_all_and_self(self):
        for executor in self._thread_pool:
            executor.stop()
        self._thread_pool.clear()
        self._task_incoming_event.set()
        self._task_queue.put(None)
        self._started.clear()
        self._manager_thread.join()
        self._manager_thread = None
        self._unlock_event = None
        self._manager_lock = None
        self._task_queue = None
        self._task_incoming_event = None


def push_task(task: BaseResponseModel):
    try:
        executor_manager = ExecutorManager.get_instance()
        executor_manager.push(task)
    except RuntimeError as e:
        raise RuntimeError("Cannot push task due to executor manager not being initialized.") from e
