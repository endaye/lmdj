// Compiler-only contract fixture, included by the original Creator tsconfig.
// Do not rename to .test.ts: this file is not an executable Vitest suite.
import type {
  PerformanceFx,
  PerformanceHeaderedEvent,
  PerformanceRawEvent,
} from "@lmdj/web-runtime-platform/runtime_types";
import type {CreatorPerformanceRuntimeSession} from "../src/runtime/runtime_types";

const gestureId = "40000000-0000-4000-8000-000000000201";
const gestureGeneration = "40000000-0000-4000-8000-000000000202";
const binding = {gestureId, gestureGeneration};
const nonFilterFx: readonly PerformanceFx[] = [
  "delay", "reverb", "stutter", "gate", "reverse", "crush", "cutter",
];

const engage = {kind: "fx_engage", fx: "delay", value: 500} satisfies PerformanceHeaderedEvent;
const move = {kind: "fx_move", fx: "delay", value: 600, ...binding} satisfies PerformanceHeaderedEvent;
const release = {kind: "fx_release", fx: "delay", ...binding} satisfies PerformanceHeaderedEvent;
// Nonfresh valid values remain assignable without casts.
const validNonfresh: readonly PerformanceHeaderedEvent[] = [engage, move, release];
void validNonfresh;

// Keep existing Filter, Pad and HOLD vocabulary; no new Filter closure here.
const preserved: readonly PerformanceHeaderedEvent[] = [
  {kind: "fx_engage", fx: "filter", value: 500},
  {kind: "fx_move", fx: "filter", value: 600, ...binding},
  {kind: "fx_release", fx: "filter", ...binding},
  {kind: "filter_parameter", phase: "engage", parameter: "cutoff_hz", value: 1000},
  {kind: "filter_parameter", phase: "move", parameter: "resonance_milli", value: 500, ...binding},
  {kind: "filter_release", ...binding},
  {kind: "pad_press", gestureId, slot: 7, velocity: 100},
  {kind: "pad_release", gestureId, slot: 7},
  {kind: "pad_mute", slot: 7, enabled: true},
  {kind: "pad_solo", slot: 7, enabled: false},
  {kind: "clear_pad_gates"},
  {kind: "hold_on"},
  {kind: "hold_off"},
];
void preserved;

// Fresh literal negatives target the actual HeaderedEvent export.
// @ts-expect-error Headered engage never accepts a caller's legacy gesture ID.
({kind: "fx_engage", fx: "delay", value: 500, gestureId} satisfies PerformanceHeaderedEvent);
// @ts-expect-error Headered engage never accepts a caller's generation.
({kind: "fx_engage", fx: "delay", value: 500, gestureGeneration} satisfies PerformanceHeaderedEvent);
// @ts-expect-error With exactOptionalPropertyTypes, even an undefined identity key is forbidden.
({kind: "fx_engage", fx: "delay", value: 500, gestureId: undefined} satisfies PerformanceHeaderedEvent);
// @ts-expect-error Engage requires its value.
({kind: "fx_engage", fx: "delay"} satisfies PerformanceHeaderedEvent);
// @ts-expect-error Move requires its value, independently of its valid binding.
({kind: "fx_move", fx: "delay", ...binding} satisfies PerformanceHeaderedEvent);
// @ts-expect-error A legacy move lacks the required Core generation.
({kind: "fx_move", fx: "delay", value: 600, gestureId} satisfies PerformanceHeaderedEvent);
// @ts-expect-error Move requires the recording gesture ID as well as the generation.
({kind: "fx_move", fx: "delay", value: 600, gestureGeneration} satisfies PerformanceHeaderedEvent);
// @ts-expect-error A legacy release lacks the required Core generation.
({kind: "fx_release", fx: "delay", gestureId} satisfies PerformanceHeaderedEvent);
// @ts-expect-error Release requires the recording gesture ID as well as the generation.
({kind: "fx_release", fx: "delay", gestureGeneration} satisfies PerformanceHeaderedEvent);
// @ts-expect-error Release has no value key.
({kind: "fx_release", fx: "delay", value: 600, ...binding} satisfies PerformanceHeaderedEvent);
// @ts-expect-error Release does not admit an explicitly undefined value key either.
({kind: "fx_release", fx: "delay", value: undefined, ...binding} satisfies PerformanceHeaderedEvent);
// @ts-expect-error Move value is numeric.
({kind: "fx_move", fx: "delay", value: "600", ...binding} satisfies PerformanceHeaderedEvent);
// @ts-expect-error Generation is an opaque string, not a Host counter.
({kind: "fx_move", fx: "delay", value: 600, gestureId, gestureGeneration: 1} satisfies PerformanceHeaderedEvent);
// @ts-expect-error Recording gesture identity is a string.
({kind: "fx_release", fx: "delay", gestureId: 1, gestureGeneration} satisfies PerformanceHeaderedEvent);

// Legacy compatibility positives also provide nonfresh identity negatives.
const legacyEngage = {kind: "fx_engage", fx: "delay", value: 500, gestureId} satisfies PerformanceRawEvent;
const legacyMove = {kind: "fx_move", fx: "delay", value: 600, gestureId} satisfies PerformanceRawEvent;
const legacyRelease = {kind: "fx_release", fx: "delay", gestureId} satisfies PerformanceRawEvent;
const legacy: readonly PerformanceRawEvent[] = [legacyEngage, legacyMove, legacyRelease];
void legacy;
// @ts-expect-error A nonfresh legacy engage cannot enter the HeaderedEvent union.
legacyEngage satisfies PerformanceHeaderedEvent;
// @ts-expect-error A nonfresh legacy move still lacks a Core generation.
legacyMove satisfies PerformanceHeaderedEvent;
// @ts-expect-error A nonfresh legacy release still lacks a Core generation.
legacyRelease satisfies PerformanceHeaderedEvent;
const engageWithGeneration = {...engage, gestureGeneration};
// @ts-expect-error Prohibit a nonfresh generation-bearing engage too.
engageWithGeneration satisfies PerformanceHeaderedEvent;
const engageWithBothIdentities = {...engage, ...binding};
// @ts-expect-error Core-issued engage identities must come back in the receipt.
engageWithBothIdentities satisfies PerformanceHeaderedEvent;
const releaseWithValue = {...release, value: 600};
// @ts-expect-error Nonfresh release values cannot bypass the no-value shape.
releaseWithValue satisfies PerformanceHeaderedEvent;

// This function is compiled, never invoked. It exercises Creator's inherited
// real SDK method, which intentionally accepts both runtime profiles.
export function compileSharedPerformanceCalls(session: CreatorPerformanceRuntimeSession): void {
  const request = {
    sessionId: "40000000-0000-4000-8000-000000000203",
    eventId: "40000000-0000-4000-8000-000000000204",
  };
  for (const fx of nonFilterFx) {
    const events: readonly PerformanceHeaderedEvent[] = [
      {kind: "fx_engage", fx, value: 500},
      {kind: "fx_move", fx, value: 600, ...binding},
      {kind: "fx_release", fx, ...binding},
    ];
    for (const event of events) void session.recordPerformanceEvent({...request, event});
  }
  void session.recordPerformanceEvent({...request, event: {kind: "fx_engage", fx: "delay", value: 500}});
  void session.recordPerformanceEvent({...request, event: {kind: "fx_move", fx: "delay", value: 600, ...binding}});
  void session.recordPerformanceEvent({...request, event: {kind: "fx_release", fx: "delay", ...binding}});
  void session.recordPerformanceEvent({...request, event: {kind: "fx_engage", fx: "delay", value: 500, gestureId}});
  void session.recordPerformanceEvent({...request, event: legacyMove});
  void session.recordPerformanceEvent({...request, event: legacyRelease});
  // Do not add negative assertions on this union method to infer a profile.
}
