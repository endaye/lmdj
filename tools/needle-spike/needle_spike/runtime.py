"""Drive Needle over the LMDJ tool surface and validate what comes back.

Nothing here dispatches into the Core engine. The spike answers one question -
can a 45M on-device model turn an utterance into a payload the production MCP
schema accepts - and stops at the validated payload on purpose, so the result
is reproducible without a built engine.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field

from .tool_surface import SpikeTool, build_tools, compose, schema_report

#: The engine ships anonymous usage counts unless this is set. A spike must not
#: phone home just because someone ran the bench, so the default is off.
DEFAULT_TELEMETRY = "0"

SYSTEM_PROMPT = (
    "You control an LMDJ groovebox. Map the user's request to exactly one tool "
    "call. Pads are addressed by bank 0-3 and pad 0-15. Never invent "
    "identifiers, file paths or revision numbers."
)


def _install_telemetry_default() -> None:
    os.environ.setdefault("NEEDLE_TELEMETRY", DEFAULT_TELEMETRY)


@dataclass
class HostContext:
    """The plumbing a real Host would hold; here, fixed so runs are comparable."""

    project_path: str = "/tmp/lmdj-needle-spike/project.lmdj"
    expected_revision: int = 7
    runtime_frame: int = 0
    session_id: str = "3f2504e0-4f89-11d3-9a0c-0305e82c3301"
    import_token: str = "9c5b94b1-35ad-49bb-b118-8e8fc24abf80"
    attempt_id: str = "16fd2706-8baf-433b-82eb-8c7fada847da"

    # Entity references a real Host would resolve from the utterance's nouns
    # against current Project Truth. Fixed here so the spike measures the model,
    # not a name-resolution step it does not implement.
    project_id: str = "5c4b1a72-2d3e-41f6-9b8a-7c1d0e2f3a4b"
    pattern_id: str = "8a3f1d20-6c47-4b91-8e52-0d9a7b6c5e41"
    asset_id: str = "b7e21c48-9f30-4a6d-92c1-5e8047af3d6b"
    destination_pattern_id: str = "8a3f1d20-6c47-4b91-8e52-0d9a7b6c5e41"
    next_pattern_id: str = "d41c8f96-7b25-4e83-a1d0-6f2b9c3e5a78"

    def resolve(self) -> dict:
        """Snapshot the plumbing, minting a fresh command_id per command."""
        return {
            "project_path": self.project_path,
            "command_id": str(uuid.uuid4()),
            "expected_revision": self.expected_revision,
            "runtime_frame": self.runtime_frame,
            "session_id": self.session_id,
            "import_token": self.import_token,
            "attempt_id": self.attempt_id,
            "project_id": self.project_id,
            "pattern_id": self.pattern_id,
            "asset_id": self.asset_id,
            "destination_pattern_id": self.destination_pattern_id,
            "next_pattern_id": self.next_pattern_id,
        }


@dataclass
class Resolution:
    """What the spike learned from one utterance."""

    utterance: str
    envelope_type: str | None = None
    #: The MCP wire name, resolved from the alias the model answered with.
    tool_name: str | None = None
    #: The alias as the model said it, kept so misroutes are readable.
    model_tool_name: str | None = None
    model_arguments: dict = field(default_factory=dict)
    payload: dict | None = None
    schema_valid: bool = False
    schema_reasons: tuple[str, ...] = ()
    confidence: float | None = None
    #: "query" or "command", taken from the MCP tool table.
    tool_surface: str | None = None
    latency_ms: float = 0.0
    peak_ram_mb: float | None = None
    decode_tps: float | None = None
    error: str | None = None

    @property
    def called_a_tool(self) -> bool:
        return self.model_tool_name is not None

    @property
    def auto_dispatchable(self) -> bool:
        """Whether a Host could run this without asking the player first.

        The gate is the MCP tool table's own `query` / `command` split, not the
        model's confidence. Measured on this intent set, confidence runs *anti*
        -correlated with correctness - wrong calls median 0.995, correct ones
        0.79-0.86 - and it drifts between runs whose routing does not, so
        thresholding it would licence exactly the wrong dispatches. A query that
        misroutes returns the wrong reading; a command that misroutes mutates
        Project Truth, so commands always need confirmation.
        """
        return (
            self.schema_valid
            and self.tool_surface == "query"
            and self.error is None
        )


class NeedleRouter:
    """A Needle agent bound to the LMDJ tool surface."""

    def __init__(
        self,
        surface: str = "performance",
        naming: str = "verb",
        system: str = SYSTEM_PROMPT,
    ):
        _install_telemetry_default()
        # Imported here, not at module scope, so the surface and the tests
        # that only exercise it stay usable without the package installed.
        import needle

        self._needle = needle
        self.surface = surface
        self.naming = naming
        self.tools: tuple[SpikeTool, ...] = build_tools(surface)
        # The model answers with the alias; everything downstream of this map
        # speaks the authoritative MCP wire name.
        self._by_model_name = {tool.model_name(naming): tool for tool in self.tools}
        started = time.perf_counter()
        self._agent = needle.Needle(
            tools=[tool.needle_tool(naming) for tool in self.tools],
            system=system,
        )
        self.init_ms = (time.perf_counter() - started) * 1000.0

    @property
    def engine_version(self) -> str:
        from needle.agent import fetch

        return fetch.ENGINE_VERSION

    @property
    def package_version(self) -> str:
        return self._needle.__version__

    def resolve(self, utterance: str, host: HostContext | None = None) -> Resolution:
        """Turn one utterance into a composed, schema-checked payload."""
        host = host or HostContext()
        result = Resolution(utterance=utterance)

        started = time.perf_counter()
        try:
            # `complete`, not `run`: the spike inspects the proposed call and
            # never executes it, so no tool body runs and no state moves.
            envelope = self._agent.complete(utterance)
        except Exception as error:  # engine faults are a finding, not a crash
            result.error = f"{type(error).__name__}: {error}"
            result.latency_ms = (time.perf_counter() - started) * 1000.0
            return result
        result.latency_ms = (time.perf_counter() - started) * 1000.0

        result.envelope_type = envelope.get("type")
        result.confidence = envelope.get("confidence")
        result.peak_ram_mb = envelope.get("peak_ram_mb")
        result.decode_tps = envelope.get("decode_tps")

        calls = envelope.get("function_calls") or []
        if not calls:
            return result
        call = calls[0]
        result.model_tool_name = call.get("name")
        result.model_arguments = call.get("arguments") or {}

        tool = self._by_model_name.get(result.model_tool_name)
        if tool is None:
            result.schema_reasons = (f"tool not on the {self.surface} surface",)
            return result
        result.tool_name = tool.name
        result.tool_surface = tool.surface

        result.payload = compose(tool, result.model_arguments, host.resolve())
        result.schema_valid, result.schema_reasons = schema_report(tool, result.payload)
        return result

    def reset(self) -> None:
        self._agent.reset()
