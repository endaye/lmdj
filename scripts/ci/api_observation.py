"""Bounded diagnostic counters for real shared-client HTTP opener attempts.

No request data or URLs are retained. One CLI process owns the observation;
its worker threads and client instances share it. This is neither an audit
journal nor a billing/health decision. Forced termination can lose the tail.
"""
from functools import wraps
from http.client import HTTPMessage
import json
import os
from threading import Lock
from time import monotonic
from urllib.error import HTTPError, URLError

_active = None
_ROLES = {'entry', 'report', 'discovery', 'relay'}
_FAMILIES = ('rest', 'graphql', 'artifact')


def _header(headers, name):
    if type(headers) is not HTTPMessage:
        return None
    values = headers.get_all(name, [])
    return values[0] if len(values) == 1 and type(values[0]) is str else None


class Observation:
    def __init__(self, role):
        self.role = role
        self.started = monotonic()
        self.lock = Lock()
        self.requests = dict.fromkeys(_FAMILIES, 0)
        self.responses = dict.fromkeys(('1xx', '2xx', '3xx', '4xx', '5xx', 'unavailable'), 0)
        self.completed = self.transport_errors = 0
        self.remaining = {}

    def begin(self, family):
        with self.lock:
            self.requests[family] += 1

    def finish(self, family, status, headers, transport_error=False):
        with self.lock:
            group = f'{status // 100}xx' if type(status) is int and 100 <= status < 600 else 'unavailable'
            self.responses[group] += 1
            self.transport_errors += int(transport_error)
            self.completed += 1
            # Third-party artifact headers never stand for GitHub quota.
            if family != 'artifact':
                resource = _header(headers, 'x-ratelimit-resource')
                raw = _header(headers, 'x-ratelimit-remaining')
                if resource in ('core', 'graphql', 'search') and raw is not None and 1 <= len(raw) <= 12 \
                        and raw.isascii() and raw.isdecimal():
                    value = int(raw)
                    self.remaining[resource] = min(self.remaining.get(resource, value), value)
            if self.completed % 100 == 0:
                self._emit('checkpoint')

    def _emit(self, phase):
        if not sum(self.requests.values()):
            return
        document = {'schema': 'lmdj.ci-api-observation.v1', 'role': self.role,
            'process_id': os.getpid(), 'phase': phase,
            'elapsed_ms': max(0, int((monotonic() - self.started) * 1000)),
            'requests': self.requests, 'responses': self.responses,
            'completed': self.completed, 'transport_errors': self.transport_errors,
            'minimum_remaining': self.remaining}
        try:
            print(json.dumps(document, sort_keys=True), flush=True)
        except Exception:
            # Lost diagnostic output cannot turn a known POST into a retry.
            pass

    def final(self):
        with self.lock:
            self._emit('final')


def observe(role):
    """Opt in only at a real CLI entry; never change its result or exception."""
    if role not in _ROLES:
        raise ValueError('why: unknown API observation role; remedy: use a closed CLI role')
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            global _active
            previous, current = _active, Observation(role)
            _active = current
            try:
                return function(*args, **kwargs)
            finally:
                _active = previous
                current.final()
        return wrapped
    return decorate


def observed_open(opener, request, *, family, timeout):
    """One opener invocation; credential-free redirects inside it are separate."""
    current = _active
    if current is None:
        return opener.open(request, timeout=timeout)
    current.begin(family)
    status, headers, transport_error = None, None, False
    try:
        response = opener.open(request, timeout=timeout)
        status, headers = getattr(response, 'status', None), getattr(response, 'headers', None)
        return response
    except HTTPError as error:
        status, headers = error.code, error.headers
        raise
    except (URLError, TimeoutError, OSError):
        transport_error = True
        raise
    finally:
        current.finish(family, status, headers, transport_error)
