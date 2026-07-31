"""Strict ctypes ownership boundary for the LMDJ Core C ABI."""

from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
from typing import Any


REQUEST_LIMIT = 16 * 1024 * 1024


class CApiError(RuntimeError):
    """A C ABI load, ownership, status, or response contract failure."""


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _reject_nonstandard_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def has_only_unicode_scalars(value: object) -> bool:
    """Return whether every string can be encoded as strict UTF-8."""
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, str):
            try:
                current.encode("utf-8", errors="strict")
            except UnicodeEncodeError:
                return False
        elif isinstance(current, list):
            pending.extend(current)
        elif isinstance(current, dict):
            pending.extend(current.keys())
            pending.extend(current.values())
    return True


def _is_lexically_normal_absolute(path: Path) -> bool:
    value = os.fspath(path)
    return path.is_absolute() and os.path.normpath(value) == value


class Engine:
    """One owned lmdj_engine handle and its five bound ABI functions."""

    def __init__(
        self,
        library_path: Path,
        workspace_root: Path,
        assembly_path: Path | None = None,
    ) -> None:
        library_path = Path(library_path)
        workspace_root = Path(workspace_root)
        if not library_path.is_absolute() or not library_path.is_file():
            raise CApiError("C ABI library path must be an existing absolute file")
        if not _is_lexically_normal_absolute(workspace_root):
            raise CApiError(
                "workspace path must be absolute and lexically normalized"
            )
        if assembly_path is not None:
            assembly_path = Path(assembly_path)
            if (
                not _is_lexically_normal_absolute(assembly_path)
                or not assembly_path.is_file()
            ):
                raise CApiError(
                    "assembly path must be an existing normalized absolute file"
                )

        try:
            self._library = ctypes.CDLL(os.fspath(library_path))
            self._bind_functions()
        except (AttributeError, OSError, TypeError) as error:
            raise CApiError("C ABI library could not be loaded") from error

        self._engine = ctypes.c_void_p()
        error_pointer = ctypes.c_void_p()
        config_value = {"workspace_root": os.fspath(workspace_root)}
        if assembly_path is not None:
            config_value["assembly_path"] = os.fspath(assembly_path)
        config = _canonical_bytes(config_value)
        diagnostic = None
        try:
            try:
                status = self._create(
                    config,
                    ctypes.byref(self._engine),
                    ctypes.byref(error_pointer),
                )
            except Exception as error:
                raise CApiError("C ABI engine creation raised") from error
            if error_pointer.value:
                try:
                    diagnostic = self._copy_string(error_pointer)
                finally:
                    self._string_free(error_pointer)
                    error_pointer = ctypes.c_void_p()
            if status != 0 or not self._engine.value or diagnostic is not None:
                raise CApiError("C ABI engine creation failed")
        except Exception:
            if error_pointer.value:
                self._string_free(error_pointer)
            if self._engine.value:
                self._engine_free(self._engine)
                self._engine = ctypes.c_void_p()
            raise

    def _bind_functions(self) -> None:
        self._create = self._library.lmdj_engine_create
        self._command = self._library.lmdj_engine_command
        self._query = self._library.lmdj_engine_query
        self._string_free = self._library.lmdj_string_free
        self._engine_free = self._library.lmdj_engine_free

        pointer = ctypes.c_void_p
        pointer_out = ctypes.POINTER(pointer)
        self._create.argtypes = [
            ctypes.c_char_p,
            pointer_out,
            pointer_out,
        ]
        self._create.restype = ctypes.c_int
        for function in (self._command, self._query):
            function.argtypes = [
                pointer,
                ctypes.c_char_p,
                pointer_out,
            ]
            function.restype = ctypes.c_int
        self._string_free.argtypes = [pointer]
        self._string_free.restype = None
        self._engine_free.argtypes = [pointer]
        self._engine_free.restype = None

    @staticmethod
    def _copy_string(pointer: ctypes.c_void_p) -> str:
        try:
            return ctypes.string_at(pointer).decode(
                "utf-8",
                errors="strict",
            )
        except (UnicodeDecodeError, ValueError, OSError) as error:
            raise CApiError("C ABI returned an invalid UTF-8 string") from error

    def _invoke(self, function: Any, request: dict) -> dict:
        if not self._engine.value:
            raise CApiError("C ABI engine is closed")
        encoded = _canonical_bytes(request)
        if len(encoded) > REQUEST_LIMIT:
            raise CApiError("C ABI request exceeds 16 MiB")

        response_pointer = ctypes.c_void_p()
        try:
            try:
                status = function(
                    self._engine,
                    encoded,
                    ctypes.byref(response_pointer),
                )
            except Exception as error:
                raise CApiError("C ABI invocation raised") from error
            if status != 0 or not response_pointer.value:
                raise CApiError("C ABI status/response contract failed")
            encoded_response = self._copy_string(response_pointer)
        finally:
            if response_pointer.value:
                self._string_free(response_pointer)

        try:
            response = json.loads(
                encoded_response,
                parse_constant=_reject_nonstandard_constant,
            )
        except (json.JSONDecodeError, ValueError, RecursionError) as error:
            raise CApiError("C ABI returned malformed JSON") from error
        if not isinstance(response, dict):
            raise CApiError("C ABI returned a non-object response")
        if not has_only_unicode_scalars(response):
            raise CApiError("C ABI returned invalid Unicode scalar data")
        return response

    def command(self, request: dict) -> dict:
        return self._invoke(self._command, request)

    def query(self, request: dict) -> dict:
        return self._invoke(self._query, request)

    def close(self) -> None:
        if self._engine.value:
            self._engine_free(self._engine)
            self._engine = ctypes.c_void_p()

    def __enter__(self) -> Engine:
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        self.close()
