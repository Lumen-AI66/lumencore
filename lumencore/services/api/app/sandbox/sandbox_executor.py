from __future__ import annotations

from contextlib import contextmanager
import builtins
import os
import socket
import subprocess
from typing import Any, Callable

_REAL_SOCKET_CONNECT = socket.socket.connect
_REAL_CREATE_CONNECTION = socket.create_connection

from .sandbox_limits import SandboxLimits
from .sandbox_policy import DEFAULT_SANDBOX_PROFILE, sandbox_limits_for_profile


@contextmanager
def restricted_environment(limits: SandboxLimits):
    original_open = builtins.open
    original_system = os.system
    original_popen = os.popen
    original_subprocess_run = subprocess.run
    original_subprocess_popen = subprocess.Popen
    original_socket_connect = socket.socket.connect
    original_create_connection = socket.create_connection

    def guarded_open(file, mode='r', *args, **kwargs):
        if not limits.filesystem_write_allowed and any(m in mode for m in ('w', 'a', '+', 'x')):
            raise PermissionError('sandbox denies filesystem write access')
        return original_open(file, mode, *args, **kwargs)

    def deny(*args, **kwargs):
        raise PermissionError('sandbox restriction')

    builtins.open = guarded_open
    if not limits.os_command_allowed:
        os.system = deny
        os.popen = deny
    if not limits.subprocess_allowed:
        subprocess.run = deny
        subprocess.Popen = deny
    if not limits.network_allowed:
        socket.socket.connect = deny
        socket.create_connection = deny

    try:
        yield
    finally:
        builtins.open = original_open
        os.system = original_system
        os.popen = original_popen
        subprocess.run = original_subprocess_run
        subprocess.Popen = original_subprocess_popen
        socket.socket.connect = original_socket_connect
        socket.create_connection = original_create_connection


@contextmanager
def allow_governed_network_calls() -> Any:
    original_socket_connect = socket.socket.connect
    original_create_connection = socket.create_connection
    socket.socket.connect = _REAL_SOCKET_CONNECT
    socket.create_connection = _REAL_CREATE_CONNECTION
    try:
        yield
    finally:
        socket.socket.connect = original_socket_connect
        socket.create_connection = original_create_connection


class SandboxExecutor:
    def __init__(self, limits: SandboxLimits | None = None, profile: str = DEFAULT_SANDBOX_PROFILE) -> None:
        self.limits = limits or sandbox_limits_for_profile(profile)

    def execute(self, task_callable: Callable[[], Any]) -> Any:
        with restricted_environment(self.limits):
            return task_callable()

