from typing import List, Dict, Optional, Any, Callable, Awaitable, TypeVar, Generic
from source.Core.ErrorHandling import CoreException

class DependencyInjectionError(CoreException):
    destination = "default"

class Injectable(metaclass=AutoInject):
    dependencies: List[str] = []
    is_dependency: bool = False
    resolved = False

class DependencyStorage:
    def __init__(self):
        self._dependencies: Dict[str, (Injectable, int)] = {}

    def add(self, name: str, dep_inst: Injectable):
        """
        Adds a dependency to the storage.
        :param name: The name of the dependency.
        :param dep_inst: The instance of the dependency.
        """
        if name in self._dependencies:
            raise DependencyInjectionError(
                "Dependency already exists",
                f"Dependency with name {name} already exists in the storage.",
                "Dependency Injection Error"
            )
        self._dependencies[name] = (dep_inst, 0)

    def resolve(self, name: str) -> Injectable:
        """
        Resolves a dependency by its name.
        :param name: The name of the dependency.
        :return: The instance of the dependency.
        """
        if name not in self._dependencies:
            raise DependencyInjectionError(
                "Dependency not found",
                f"Dependency with name {name} not found in the storage.",
                ""
            )
        self._dependencies[name][1] += 1
        return self._dependencies[name][0]


    def resolve_all_deps_after_init(self):
        """
        This is a cleanup method to ensure that all dependencies are resolved after initialization.
        It is called after all dependencies have been added to the storage and initialized.
        """
        for name, (target, _) in self._dependencies.items():
            if not target.resolved:
                dependencies_keys = [dep for dep in target.dependencies if dep in self._dependencies]
                for key in dependencies_keys:
                    setattr(target, key, self.get_dependency(key))





