from types import MappingProxyType
from source.Core.TaskScheduling import ProcessState
# Lookup tables

size_type_dict = MappingProxyType({
            "b": 1,
            "bytes": 1,
            "byte": 1,
            "kb": 1024,
            "kilobytes": 1024,
            "kilobyte": 1024,
            "mb": 1024 * 1024,
            "megabytes": 1024 * 1024,
            "megabyte": 1024 * 1024,
            "gb": 1024 * 1024 * 1024,
            "gigabytes": 1024 * 1024 * 1024,
            "gigabyte": 1024 * 1024 * 1024
        })

time_type_dict = MappingProxyType({
            "s": 1,
            "seconds": 1,
            "second": 1,
            "m": 60,
            "minutes": 60,
            "minute": 60,
            "h": 60 * 60,
            "hours": 60 * 60,
            "hour": 60 * 60,
            "d": 60 * 60 * 24,
            "days": 60 * 60 * 24,
            "day": 60 * 60 * 24
        })

process_state_dict = MappingProxyType({
    ProcessState.IDLE: "Idle",
    ProcessState.BUSY: "Busy",
    ProcessState.STOPPED: "Stopped"
})

