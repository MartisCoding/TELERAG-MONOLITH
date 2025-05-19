
"""
A file for some of utils functions used in the project.
"""
import time, abc
from typing import Any

class BaseCache:
    """
    An abstract base class for a cache.
    """
    @abc.abstractmethod
    def __setitem__(self, key: Any, value: Any) -> None:
        raise NotImplementedError("Subclasses must implement __setitem__")

    @abc.abstractmethod
    def __getitem__(self, key: Any) -> Any:
        raise NotImplementedError("Subclasses must implement __getitem__")

    @abc.abstractmethod
    def __contains__(self, key: Any) -> bool:
        raise NotImplementedError("Subclasses must implement __contains__")

    @abc.abstractmethod
    def _evict(self) -> None:
        raise NotImplementedError("Subclasses must implement _evict")

class TTLCache(BaseCache):
    """
    A simple TTL (Time To Live) cache implementation.
    This cache will store items for a specified duration and automatically remove them after that time.
    """
    def __init__(self, maxsize: int, ttl: int):
        self.cache = {}
        self.maxsize = maxsize
        self.ttl = ttl

    def __setitem__(self, key, value):
        if len(self.cache) >= self.maxsize:
            self._evict()
        expiry = time.monotonic() + self.ttl
        self.cache[key] = (value, expiry)

    def __getitem__(self, key):
        if key not in self.cache:
            raise KeyError(f"Key {key} not found in cache.")
        value, expiry = self.cache[key]
        if time.monotonic() >= expiry:
            del self.cache[key]
            raise KeyError(f"Key {key} has expired.")
        return value

    def __contains__(self, key):
        return key in self.cache

    def _evict(self):
        current_time = time.monotonic()
        keys_to_delete = [key for key, (_, expiry) in self.cache.items() if current_time >= expiry]
        for key in keys_to_delete:
            del self.cache[key]