#include <lmdj/facade/runtime_facade.hpp>

#if __has_include(<lmdj/project_io/project_store.hpp>) || \
    __has_include(<lmdj/provider/registry.hpp>)
#error "why: narrow runtime consumer sees authoring IO/Provider; remedy: link only runtime_facade"
#endif

#include <algorithm>
#include <array>
#include <cstdlib>
#include <new>
#include <vector>

#include <lmdj/audio/prepared_sample_bank.hpp>
#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/cooker/runtime_content.hpp>
#include "tests/core/support/test.hpp"

namespace {
using namespace lmdj;
using namespace lmdj::facade;
thread_local std::size_t fail_size{};
thread_local bool forbid_allocation{};
thread_local bool count_allocations{};
thread_local std::size_t allocation_count{};
thread_local std::size_t fail_at{};
thread_local bool observe_load_order{};
thread_local std::size_t observed_order{};
thread_local std::size_t engine_order{}, control_storage_order{}, outcome_storage_order{};
thread_local std::size_t voice_storage_order{}, pcm_order{};
thread_local std::size_t live_allocations{};
thread_local bool observe_sample_payloads{};
thread_local std::size_t pcm_payload_allocations{}, float_payload_allocations{};
void before_allocate(std::size_t bytes) {
  if (forbid_allocation) std::abort();
  if (observe_sample_payloads) {
    if (bytes == 8192) ++pcm_payload_allocations;
    if (bytes == 16384 || bytes == 32768) ++float_payload_allocations;
  }
  if (observe_load_order) {
    ++observed_order;
    if (bytes == sizeof(audio::RealtimeEngine)) engine_order = observed_order;
    if (bytes == 129 * sizeof(audio::PadControlEvent)) control_storage_order = observed_order;
    if (bytes == 129 * sizeof(audio::RuntimeTriggerOutcomeEvent)) outcome_storage_order = observed_order;
    if (bytes == 385 * sizeof(audio::detail::RuntimeVoiceStateCell))
      voice_storage_order = observed_order;
    if (bytes == 4096 * sizeof(std::int16_t) && pcm_order == 0)
      pcm_order = observed_order;
  }
  if (count_allocations) {
    ++allocation_count;
    if (allocation_count == fail_at) throw std::bad_alloc{};
  }
  if (fail_size != 0 && bytes >= fail_size) throw std::bad_alloc{};
}
void* allocate(std::size_t bytes) {
  before_allocate(bytes);
  if (auto* memory = std::malloc(bytes == 0 ? 1 : bytes)) {
    ++live_allocations;
    return memory;
  }
  throw std::bad_alloc{};
}
void* allocate_aligned(std::size_t bytes, std::size_t alignment) {
  before_allocate(bytes);
  void* memory{};
  if (posix_memalign(&memory, alignment, bytes == 0 ? alignment : bytes) == 0) {
    ++live_allocations;
    return memory;
  }
  throw std::bad_alloc{};
}

RuntimeConfig config() {
  return {{1'048'576, 262'144, 65'536, 64, 1024},
          16'777'216, 65'536, 128, 100, 10'000};
}

cooker::RuntimeSnapshot snapshot(bool pattern = true, bool muted = false) {
  auto pcm = std::make_shared<const cooker::PcmSample>(
      cooker::PcmSample{48'000, 1, std::vector<std::int16_t>(4096, 16384)});
  return {foundation::ProjectId{"00000000-0000-4000-8000-000000000001"},
          foundation::PatternId{"00000000-0000-4000-8000-000000000002"},
          1, 120, 1, 960, 3840,
          {{{0, 0}, {}, pcm, {0, 4096, domain::TriggerMode::one_shot, 1.0F, muted}}},
          pattern ? std::vector<cooker::ResolvedEvent>{{{0, 0}, 0, 240, 127, pcm}}
                  : std::vector<cooker::ResolvedEvent>{}};
}
cooker::EncodedRuntimeContent content(bool pattern = true, bool muted = false) {
  auto result = cooker::encode_runtime_content(snapshot(pattern, muted), config().content_limits);
  LMDJ_CHECK(result.has_value());
  return std::move(result.value());
}

struct Output {
  std::array<float, 256> left{}, right{};
  bool silent() const {
    return std::all_of(left.begin(), left.end(), [](float v) { return v == 0; }) &&
           std::all_of(right.begin(), right.end(), [](float v) { return v == 0; });
  }
  void render(RuntimeFacade& runtime) {
    left.fill(9); right.fill(9);
    forbid_allocation = true;
    runtime.render(left.data(), right.data(), left.size());
    forbid_allocation = false;
  }
};

RuntimeContentSummary summary_without_allocation(const RuntimeFacade& runtime) {
  forbid_allocation = true;
  const auto result = runtime.content_summary();
  forbid_allocation = false;
  return result;
}

void content_summary_preserves_all_canonical_slots_and_modes() {
  auto source = snapshot(false);
  const auto prototype = source.pads.front();
  source.pads.clear();
  const std::array modes{domain::TriggerMode::one_shot, domain::TriggerMode::gate,
                         domain::TriggerMode::loop_gate, domain::TriggerMode::loop_toggle};
  const std::array expected{RuntimeTriggerMode::one_shot, RuntimeTriggerMode::gate,
                            RuntimeTriggerMode::loop_gate, RuntimeTriggerMode::loop_toggle};
  for (std::uint8_t slot = 0; slot < 64; ++slot) {
    auto pad = prototype;
    pad.slot = {static_cast<std::uint8_t>(slot / 16), static_cast<std::uint8_t>(slot % 16)};
    pad.playback.trigger_mode = modes[slot % modes.size()];
    source.pads.push_back(pad);
  }
  auto encoded = cooker::encode_runtime_content(source, config().content_limits);
  LMDJ_CHECK(encoded.has_value());
  RuntimeFacade runtime(config());
  LMDJ_CHECK(runtime.load(encoded.value().bytes, encoded.value().identity) == RuntimeResult::ok);
  const auto summary = summary_without_allocation(runtime);
  LMDJ_CHECK(summary.count == 64);
  for (std::size_t slot = 0; slot < summary.count; ++slot) {
    LMDJ_CHECK(summary.pads[slot].bank == slot / 16);
    LMDJ_CHECK(summary.pads[slot].pad == slot % 16);
    LMDJ_CHECK(summary.pads[slot].trigger_mode == expected[slot % expected.size()]);
  }
}

void content_summary_tracks_publication_and_clearing() {
  const auto bytes = content();
  RuntimeFacade runtime(config());
  const RuntimeContentSummary empty{};
  LMDJ_CHECK(summary_without_allocation(runtime) == empty);
  auto wrong = bytes.identity;
  ++wrong.byte_length;
  LMDJ_CHECK(runtime.load(bytes.bytes, wrong) == RuntimeResult::invalid_content);
  LMDJ_CHECK(summary_without_allocation(runtime) == empty);
  LMDJ_CHECK(runtime.load(bytes.bytes, bytes.identity) == RuntimeResult::ok);
  const auto ready = summary_without_allocation(runtime);
  LMDJ_CHECK(ready.count == 1);
  LMDJ_CHECK(ready.pads[0] == (RuntimePadSummary{0, 0, RuntimeTriggerMode::one_shot}));
  RuntimeEpoch epoch;
  LMDJ_CHECK(runtime.start(epoch) == RuntimeResult::ok);
  LMDJ_CHECK(summary_without_allocation(runtime) == ready);
  runtime.request_stop();
  LMDJ_CHECK(summary_without_allocation(runtime) == ready);
  LMDJ_CHECK(runtime.finish_stop() == RuntimeResult::ok);
  LMDJ_CHECK(summary_without_allocation(runtime) == ready);
  LMDJ_CHECK(runtime.unload() == RuntimeResult::ok);
  LMDJ_CHECK(summary_without_allocation(runtime) == empty);
  LMDJ_CHECK(runtime.load(bytes.bytes, bytes.identity) == RuntimeResult::ok);
  LMDJ_CHECK(summary_without_allocation(runtime) == ready);
  runtime.reset();
  LMDJ_CHECK(summary_without_allocation(runtime) == empty);
  // A returned value owns no pointers into content reclaimed by unload/reset.
  LMDJ_CHECK(ready.count == 1);
  LMDJ_CHECK(ready.pads[0] == (RuntimePadSummary{0, 0, RuntimeTriggerMode::one_shot}));
}

void lifecycle_journey() {
  const auto bytes = content();
  RuntimeFacade runtime(config());
  Output output;
  RuntimeEpoch first;
  LMDJ_CHECK(runtime.phase() == RuntimePhase::empty);
  LMDJ_CHECK(!runtime.content_identity().has_value());
  output.render(runtime); LMDJ_CHECK(output.silent());
  LMDJ_CHECK(runtime.start(first) == RuntimeResult::wrong_state);
  LMDJ_CHECK(runtime.load(bytes.bytes, bytes.identity) == RuntimeResult::ok);
  LMDJ_CHECK(runtime.phase() == RuntimePhase::ready);
  LMDJ_CHECK(runtime.content_identity() == bytes.identity);
  output.render(runtime); LMDJ_CHECK(output.silent());
  LMDJ_CHECK(runtime.start(first) == RuntimeResult::ok);
  output.render(runtime); LMDJ_CHECK(!output.silent());
  LMDJ_CHECK(runtime.unload() == RuntimeResult::wrong_state);
  runtime.request_stop();
  LMDJ_CHECK(runtime.phase() == RuntimePhase::draining);
  output.render(runtime); LMDJ_CHECK(output.silent());
  LMDJ_CHECK(runtime.unload() == RuntimeResult::wrong_state);
  LMDJ_CHECK(runtime.finish_stop() == RuntimeResult::ok);
  LMDJ_CHECK(runtime.phase() == RuntimePhase::stopped);
  RuntimeEpoch second;
  LMDJ_CHECK(runtime.start(second) == RuntimeResult::ok);
  LMDJ_CHECK(first != second);
  LMDJ_CHECK(runtime.submit({first, 1}) == RuntimeResult::stale_epoch);
  output.render(runtime); LMDJ_CHECK(!output.silent());
  runtime.stop(); LMDJ_CHECK(runtime.phase() == RuntimePhase::stopped);
  LMDJ_CHECK(runtime.unload() == RuntimeResult::ok);
  LMDJ_CHECK(runtime.phase() == RuntimePhase::empty);
  output.render(runtime); LMDJ_CHECK(output.silent());
  auto bad = bytes.identity; ++bad.byte_length;
  LMDJ_CHECK(runtime.load(bytes.bytes, bad) == RuntimeResult::invalid_content);
  LMDJ_CHECK(runtime.phase() == RuntimePhase::empty);
  output.render(runtime); LMDJ_CHECK(output.silent());
  LMDJ_CHECK(runtime.load(bytes.bytes, bytes.identity) == RuntimeResult::ok);
  RuntimeEpoch third;
  LMDJ_CHECK(runtime.start(third) == RuntimeResult::ok);
  LMDJ_CHECK(runtime.submit({second, 1}) == RuntimeResult::stale_epoch);
  output.render(runtime); LMDJ_CHECK(!output.silent());
  runtime.reset(); LMDJ_CHECK(runtime.phase() == RuntimePhase::empty);
  LMDJ_CHECK(!runtime.content_identity().has_value());
  output.render(runtime); LMDJ_CHECK(output.silent());
  LMDJ_CHECK(runtime.load(bytes.bytes, bytes.identity) == RuntimeResult::ok);
  RuntimeEpoch fourth;
  LMDJ_CHECK(runtime.start(fourth) == RuntimeResult::ok);
  LMDJ_CHECK(runtime.submit({third, 1}) == RuntimeResult::stale_epoch);
  output.render(runtime); LMDJ_CHECK(!output.silent());
}

void receipts_and_retry() {
  const auto bytes = content(false);
  auto limits = config(); limits.maximum_pending_commands = 1;
  RuntimeFacade runtime(limits);
  LMDJ_CHECK(runtime.load(bytes.bytes, bytes.identity) == RuntimeResult::ok);
  RuntimeEpoch epoch;
  LMDJ_CHECK(runtime.start(epoch) == RuntimeResult::ok);
  std::array<RuntimeReceipt, 2> receipts;
  LMDJ_CHECK(runtime.submit({epoch, 2}) == RuntimeResult::out_of_order);
  LMDJ_CHECK(runtime.submit({epoch, 1, RuntimeCommandKind::press, 64}) == RuntimeResult::invalid_command);
  LMDJ_CHECK(runtime.submit({epoch, 1}) == RuntimeResult::accepted);
  LMDJ_CHECK(runtime.poll(receipts) == 0);
  LMDJ_CHECK(runtime.submit({epoch, 1}) == RuntimeResult::duplicate_sequence);
  RuntimeCommand retry{epoch, 2, RuntimeCommandKind::stop_all};
  LMDJ_CHECK(runtime.submit(retry) == RuntimeResult::queue_full);
  Output output; output.render(runtime); LMDJ_CHECK(!output.silent());
  LMDJ_CHECK(runtime.poll(receipts) == 1);
  LMDJ_CHECK(receipts[0].sequence == 1 && receipts[0].epoch == epoch);
  LMDJ_CHECK(receipts[0].outcome == RuntimeCommandOutcome::voice_started);
  LMDJ_CHECK(runtime.submit(retry) == RuntimeResult::accepted);
  runtime.stop();
  LMDJ_CHECK(runtime.poll(receipts) == 1);
  LMDJ_CHECK(receipts[0].sequence == 2);
  LMDJ_CHECK(receipts[0].outcome == RuntimeCommandOutcome::cancelled);
  LMDJ_CHECK(runtime.poll(receipts) == 0);
  output.render(runtime); LMDJ_CHECK(output.silent());
  RuntimeEpoch next;
  LMDJ_CHECK(runtime.start(next) == RuntimeResult::ok);
  LMDJ_CHECK(runtime.submit({next, 1, RuntimeCommandKind::stop_all}) == RuntimeResult::accepted);
  output.render(runtime); LMDJ_CHECK(output.silent());
  LMDJ_CHECK(runtime.poll(receipts) == 1);
  LMDJ_CHECK(receipts[0].outcome == RuntimeCommandOutcome::applied);
}

void fixed_budget_tracks_pending_admission() {
  const auto bytes = content(false);
  std::uint64_t previous = 0;
  for (const std::uint32_t pending : {1U, 128U, 1024U}) {
    auto limits = config();
    limits.maximum_pending_commands = pending;
    RuntimeFacade runtime(limits);
    LMDJ_CHECK(runtime.load(bytes.bytes, bytes.identity) == RuntimeResult::ok);
    const auto fixed = runtime.budget().fixed_bytes;
    if (previous != 0) {
      const auto previous_pending = pending == 128 ? 1U : 128U;
      const auto expected_growth = (pending - previous_pending) *
          (sizeof(audio::PadControlEvent) + sizeof(audio::RuntimeTriggerOutcomeEvent) +
           2 * sizeof(audio::detail::RuntimeVoiceStateCell));
      LMDJ_CHECK(fixed - previous == expected_growth);
    }
    test::check(fixed > previous,
                "why: pending admission does not size fixed queue storage; "
                "remedy: construct and account for the explicit N profile; N=" +
                    std::to_string(pending) + " fixed=" + std::to_string(fixed) +
                    " previous=" + std::to_string(previous));
    previous = fixed;
  }
}

void shared_pcm_load_has_one_payload_and_no_float_allocation() {
  observe_sample_payloads = true;
  pcm_payload_allocations = float_payload_allocations = 0;
  auto* ordinary = ::operator new(8192);
  auto* aligned = ::operator new(16384, std::align_val_t{64});
  ::operator delete(ordinary);
  ::operator delete(aligned, std::align_val_t{64});
  observe_sample_payloads = false;
  LMDJ_CHECK(pcm_payload_allocations == 1 && float_payload_allocations == 1);

  auto source = snapshot(false);
  auto second = source.pads[0];
  second.slot = {0, 1};
  second.playback = {128, 2048, domain::TriggerMode::gate, 0.5F, false};
  source.pads.push_back(std::move(second));
  const auto bytes = cooker::encode_runtime_content(source, config().content_limits);
  LMDJ_CHECK(bytes.has_value());
  const auto footprint = cooker::inspect_runtime_content(
      bytes.value().bytes, bytes.value().identity, config().content_limits);
  LMDJ_CHECK(footprint.has_value());
  LMDJ_CHECK(footprint.value().pcm_bytes == 8192);
  LMDJ_CHECK(footprint.value().prepared_float_bytes == 32768);
  RuntimeFacade runtime(config());
  pcm_payload_allocations = float_payload_allocations = 0;
  observe_sample_payloads = true;
  const auto loaded = runtime.load(bytes.value().bytes, bytes.value().identity);
  observe_sample_payloads = false;
  LMDJ_CHECK(loaded == RuntimeResult::ok);
  LMDJ_CHECK(pcm_payload_allocations == 1 && float_payload_allocations == 0);
  LMDJ_CHECK(runtime.budget().pcm_bytes == 8192);
  LMDJ_CHECK(runtime.budget().prepared_float_bytes == 0);
  RuntimeEpoch epoch;
  LMDJ_CHECK(runtime.start(epoch) == RuntimeResult::ok);
  LMDJ_CHECK(runtime.submit({epoch, 1, RuntimeCommandKind::press, 0}) == RuntimeResult::accepted);
  LMDJ_CHECK(runtime.submit({epoch, 2, RuntimeCommandKind::press, 1}) == RuntimeResult::accepted);
  Output output;
  output.render(runtime);
  LMDJ_CHECK(!output.silent());
  std::array<RuntimeReceipt, 2> receipts;
  LMDJ_CHECK(runtime.poll(receipts) == 2);
  LMDJ_CHECK(receipts[0].outcome == RuntimeCommandOutcome::voice_started);
  LMDJ_CHECK(receipts[1].outcome == RuntimeCommandOutcome::voice_started);
  runtime.reset();
  LMDJ_CHECK(!runtime.content_identity());
  output.render(runtime);
  LMDJ_CHECK(output.silent());
}

void budget_and_allocation_retry() {
  const auto bytes = content();
  auto limits = config();
  RuntimeFacade measuring(limits);
  LMDJ_CHECK(measuring.load(bytes.bytes, bytes.identity) == RuntimeResult::ok);
  const auto budget = measuring.budget();
  LMDJ_CHECK(budget.fixed_bytes > 0 && budget.metadata_bytes > 0);
  LMDJ_CHECK(budget.encoded_bytes == bytes.bytes.size());
  LMDJ_CHECK(budget.pcm_bytes == 8192);
  LMDJ_CHECK(budget.prepared_float_bytes == 0);
  LMDJ_CHECK(budget.preparation_workspace_bytes ==
      sizeof(lmdj::audio::PreparedSampleBank) +
      sizeof(lmdj::audio::PreparedPatternView) + sizeof(domain::PatternEvent));
  limits.maximum_admitted_bytes = budget.admitted_bytes;
  RuntimeFacade exact(limits);
  LMDJ_CHECK(exact.load(bytes.bytes, bytes.identity) == RuntimeResult::ok);
  --limits.maximum_admitted_bytes;
  RuntimeFacade refused(limits);
  LMDJ_CHECK(refused.load(bytes.bytes, bytes.identity) == RuntimeResult::budget_exceeded);
  LMDJ_CHECK(refused.phase() == RuntimePhase::empty);
  Output output; output.render(refused); LMDJ_CHECK(output.silent());
  RuntimeFacade failing(config());
  fail_size = 8192;
  const auto result = failing.load(bytes.bytes, bytes.identity);
  fail_size = 0;
  LMDJ_CHECK(result == RuntimeResult::allocation_failed);
  LMDJ_CHECK(failing.phase() == RuntimePhase::empty);
  output.render(failing); LMDJ_CHECK(output.silent());
  LMDJ_CHECK(failing.load(bytes.bytes, bytes.identity) == RuntimeResult::ok);
  RuntimeEpoch epoch;
  LMDJ_CHECK(failing.start(epoch) == RuntimeResult::ok);
  output.render(failing); LMDJ_CHECK(!output.silent());
  limits = config(); limits.platform_reserve_bytes = UINT64_MAX;
  RuntimeFacade overflow(limits);
  LMDJ_CHECK(overflow.load(bytes.bytes, bytes.identity) == RuntimeResult::budget_exceeded);
  limits.maximum_pending_commands = 0;
  RuntimeFacade invalid(limits);
  LMDJ_CHECK(invalid.load(bytes.bytes, bytes.identity) == RuntimeResult::invalid_config);
}

void counters_and_receipt_retention() {
  const auto bytes = content(false);
  auto limits = config(); limits.maximum_epoch = 1; limits.maximum_sequence = 1;
  RuntimeFacade runtime(limits);
  LMDJ_CHECK(runtime.load(bytes.bytes, bytes.identity) == RuntimeResult::ok);
  RuntimeEpoch epoch;
  LMDJ_CHECK(runtime.start(epoch) == RuntimeResult::ok);
  LMDJ_CHECK(runtime.submit({epoch, 1}) == RuntimeResult::accepted);
  LMDJ_CHECK(runtime.submit({epoch, 2}) == RuntimeResult::sequence_exhausted);
  runtime.reset();
  LMDJ_CHECK(runtime.load(bytes.bytes, bytes.identity) == RuntimeResult::ok);
  RuntimeEpoch unchanged;
  LMDJ_CHECK(runtime.start(unchanged) == RuntimeResult::wrong_state);
  std::array<RuntimeReceipt, 1> receipt;
  LMDJ_CHECK(runtime.poll(receipt) == 1);
  LMDJ_CHECK(receipt[0].epoch == epoch && receipt[0].outcome == RuntimeCommandOutcome::cancelled);
  LMDJ_CHECK(runtime.start(unchanged) == RuntimeResult::epoch_exhausted);
  LMDJ_CHECK(unchanged == RuntimeEpoch{});
  RuntimeFacade another(config());
  LMDJ_CHECK(another.load(bytes.bytes, bytes.identity) == RuntimeResult::ok);
  RuntimeEpoch other;
  LMDJ_CHECK(another.start(other) == RuntimeResult::ok);
  LMDJ_CHECK(other != epoch);
  LMDJ_CHECK(another.submit({epoch, 1}) == RuntimeResult::stale_epoch);
}

void allocator_controls_cover_ordinary_and_aligned_storage() {
  const auto before = live_allocations;
  allocation_count = 0; count_allocations = true;
  auto* ordinary = ::operator new(37);
  auto* aligned = ::operator new(129, std::align_val_t{64});
  count_allocations = false;
  LMDJ_CHECK(allocation_count == 2 && live_allocations == before + 2);
  LMDJ_CHECK(reinterpret_cast<std::uintptr_t>(aligned) % 64 == 0);
  ::operator delete(ordinary);
  ::operator delete(aligned, std::align_val_t{64});
  LMDJ_CHECK(live_allocations == before);
}

void every_load_allocation_failure_stays_empty(std::uint32_t pending) {
  const auto bytes = content();
  auto limits = config(); limits.maximum_pending_commands = pending;
  RuntimeFacade measuring(limits);
  allocation_count = 0; fail_at = 0; count_allocations = true;
  const auto measured = measuring.load(bytes.bytes, bytes.identity);
  count_allocations = false;
  const auto allocation_sites = allocation_count;
  LMDJ_CHECK(measured == RuntimeResult::ok && allocation_sites > 0);
  for (std::size_t site = 1; site <= allocation_sites; ++site) {
    RuntimeFacade runtime(limits);
    const auto live_before = live_allocations;
    allocation_count = 0; fail_at = site; count_allocations = true;
    const auto result = runtime.load(bytes.bytes, bytes.identity);
    count_allocations = false; fail_at = 0;
    LMDJ_CHECK(live_allocations == live_before);
    test::check(result == RuntimeResult::allocation_failed,
                "allocation failure site " + std::to_string(site) +
                    " of " + std::to_string(allocation_sites) +
                    "; actual allocations " + std::to_string(allocation_count));
    LMDJ_CHECK(runtime.phase() == RuntimePhase::empty);
    LMDJ_CHECK(!runtime.content_identity().has_value());
    LMDJ_CHECK(summary_without_allocation(runtime) == RuntimeContentSummary{});
    Output output; output.render(runtime); LMDJ_CHECK(output.silent());
    LMDJ_CHECK(runtime.load(bytes.bytes, bytes.identity) == RuntimeResult::ok);
    RuntimeEpoch epoch;
    LMDJ_CHECK(runtime.start(epoch) == RuntimeResult::ok);
    output.render(runtime); LMDJ_CHECK(!output.silent());
    runtime.reset(); LMDJ_CHECK(runtime.phase() == RuntimePhase::empty);
  }
}

void load_uses_and_accounts_for_the_receipt_bounded_storage() {
  const auto bytes = content();
  RuntimeFacade runtime(config());
  // Reject a default 10240-entry allocation (and the original inline Engine).
  // The receipt-bounded Engine and queue must each fit below this size.
  fail_size = sizeof(audio::detail::RuntimeVoiceStateStorage::Full);
  const auto loaded = runtime.load(bytes.bytes, bytes.identity);
  fail_size = 0;
  LMDJ_CHECK(loaded == RuntimeResult::ok);
  LMDJ_CHECK(runtime.budget().fixed_bytes >=
      sizeof(RuntimeFacade) + sizeof(audio::RealtimeEngine) +
      *audio::RealtimeEngine::receipt_bounded_storage_bytes(config().maximum_pending_commands));
}

void load_allocates_fixed_storage_before_pcm() {
  // Observe actual allocations through the public load boundary. This guards
  // ordering, not a simulation of ESP-IDF's multi-region allocator: the real
  // fragmented-heap and DMA journey is retained in the Cardputer evidence.
  const auto bytes = content(false);
  RuntimeFacade runtime(config());
  observed_order = engine_order = voice_storage_order = pcm_order = 0;
  control_storage_order = outcome_storage_order = 0;
  observe_load_order = true;
  const auto result = runtime.load(bytes.bytes, bytes.identity);
  observe_load_order = false;
  LMDJ_CHECK(result == RuntimeResult::ok);
  test::check(engine_order != 0 && control_storage_order != 0 &&
                  outcome_storage_order != 0 && voice_storage_order != 0 && pcm_order != 0 &&
                  engine_order < pcm_order && control_storage_order < pcm_order &&
                  outcome_storage_order < pcm_order && voice_storage_order < pcm_order,
              "why: variable PCM fragments the heap before fixed storage; "
              "remedy: allocate candidate Engine and queue before decoding PCM; "
              "Engine=" + std::to_string(engine_order) + " queue=" +
                  std::to_string(voice_storage_order) + " PCM=" + std::to_string(pcm_order));
}

void old_voice_terminals_and_full_pending_batch_preserve_receipts(std::uint32_t pending) {
  auto source = snapshot(false);
  auto short_pcm = std::make_shared<const cooker::PcmSample>(
      cooker::PcmSample{48'000, 1, {16384, 16384, 16384, 16384}});
  source.pads.push_back({{0, 1}, {}, short_pcm,
                        {0, 4, domain::TriggerMode::one_shot, 1.0F, false}});
  const auto encoded = cooker::encode_runtime_content(source, config().content_limits);
  LMDJ_CHECK(encoded.has_value());
  const auto& bytes = encoded.value();
  auto limits = config(); limits.maximum_pending_commands = pending;
  RuntimeFacade runtime(limits);
  LMDJ_CHECK(runtime.load(bytes.bytes, bytes.identity) == RuntimeResult::ok);
  RuntimeEpoch epoch;
  LMDJ_CHECK(runtime.start(epoch) == RuntimeResult::ok);
  std::array<RuntimeReceipt, 1> initial;
  for (std::uint32_t sequence = 1; sequence <= 128; ++sequence) {
    LMDJ_CHECK(runtime.submit({epoch, sequence}) == RuntimeResult::accepted);
    float left{}, right{};
    forbid_allocation = true;
    runtime.render(&left, &right, 1);
    forbid_allocation = false;
    LMDJ_CHECK(runtime.poll(initial) == 1);
    LMDJ_CHECK(initial[0].sequence == sequence);
    LMDJ_CHECK(initial[0].outcome == RuntimeCommandOutcome::voice_started);
  }
  // The starts have been acknowledged/drained. All 128 old voices now end
  // without another poll, accounting for the + Voices term of 2*N + Voices.
  Output output;
  for (int block = 0; block < 16; ++block) output.render(runtime);
  std::array<float, 4> left{}, right{};
  const auto render_short = [&] {
    forbid_allocation = true;
    runtime.render(left.data(), right.data(), left.size());
    forbid_allocation = false;
    LMDJ_CHECK(left[1] > 0 && right[1] > 0);
  };
  for (std::uint32_t sequence = 129; sequence <= 128 + pending; ++sequence) {
    LMDJ_CHECK(runtime.submit({epoch, sequence, RuntimeCommandKind::press, 1}) ==
               RuntimeResult::accepted);
    render_short();
  }
  // Exactly 128 old terminals + N * (started, completed) unread states.
  const RuntimeCommand retry{epoch, 129 + pending, RuntimeCommandKind::press, 1};
  LMDJ_CHECK(runtime.submit(retry) == RuntimeResult::queue_full);
  LMDJ_CHECK(runtime.poll({}) == 0);
  LMDJ_CHECK(runtime.submit(retry) == RuntimeResult::queue_full);
  std::array<RuntimeReceipt, 1> receipt;
  LMDJ_CHECK(runtime.poll(receipt) == 1);
  LMDJ_CHECK(receipt[0].sequence == 129 && receipt[0].epoch == epoch);
  LMDJ_CHECK(receipt[0].outcome == RuntimeCommandOutcome::voice_started);
  LMDJ_CHECK(runtime.submit(retry) == RuntimeResult::accepted);
  render_short();
  for (std::uint32_t sequence = 130; sequence <= 129 + pending; ++sequence) {
    LMDJ_CHECK(runtime.poll(receipt) == 1);
    LMDJ_CHECK(receipt[0].epoch == epoch && receipt[0].sequence == sequence);
    LMDJ_CHECK(receipt[0].outcome == RuntimeCommandOutcome::voice_started);
  }
  LMDJ_CHECK(runtime.poll(receipt) == 0);
  runtime.stop();
  LMDJ_CHECK(runtime.unload() == RuntimeResult::ok);
  output.render(runtime); LMDJ_CHECK(output.silent());
}

void canonical_preparation_rejects_duplicate_order() {
  auto source = snapshot();
  LMDJ_CHECK(audio::PreparedPatternView::from_canonical_snapshot(source).has_value());
  source.events.push_back(source.events.front());
  LMDJ_CHECK(!audio::PreparedPatternView::from_canonical_snapshot(source).has_value());
  // Desktop normalization retains its existing duplicate-key semantics.
  LMDJ_CHECK(audio::PreparedPatternView::from_snapshot(source).has_value());
}

void voice_refusal_is_not_a_started_receipt() {
  auto limits = config(); limits.maximum_pending_commands = 1024;
  RuntimeFacade runtime(limits);
  const auto bytes = content(false);
  LMDJ_CHECK(runtime.load(bytes.bytes, bytes.identity) == RuntimeResult::ok);
  RuntimeEpoch epoch;
  LMDJ_CHECK(runtime.start(epoch) == RuntimeResult::ok);
  for (std::uint32_t sequence = 1; sequence <= 129; ++sequence) {
    LMDJ_CHECK(runtime.submit({epoch, sequence}) == RuntimeResult::accepted);
  }
  float left{}, right{};
  runtime.render(&left, &right, 1);
  std::array<RuntimeReceipt, 129> receipts;
  LMDJ_CHECK(runtime.poll(receipts) == 129);
  for (std::size_t index = 0; index < 128; ++index) {
    LMDJ_CHECK(receipts[index].sequence == index + 1);
    LMDJ_CHECK(receipts[index].outcome == RuntimeCommandOutcome::voice_started);
  }
  LMDJ_CHECK(receipts.back().sequence == 129);
  LMDJ_CHECK(receipts.back().outcome == RuntimeCommandOutcome::voice_capacity);
}

void muted_apply_is_not_a_started_receipt() {
  RuntimeFacade runtime(config());
  const auto bytes = content(false, true);
  LMDJ_CHECK(runtime.load(bytes.bytes, bytes.identity) == RuntimeResult::ok);
  RuntimeEpoch epoch;
  LMDJ_CHECK(runtime.start(epoch) == RuntimeResult::ok);
  LMDJ_CHECK(runtime.submit({epoch, 1}) == RuntimeResult::accepted);
  Output output; output.render(runtime); LMDJ_CHECK(output.silent());
  std::array<RuntimeReceipt, 1> receipt;
  LMDJ_CHECK(runtime.poll(receipt) == 1);
  LMDJ_CHECK(receipt[0].outcome == RuntimeCommandOutcome::applied);
}

void receipt_ring_wrap_preserves_order() {
  RuntimeFacade runtime(config());
  const auto bytes = content(false);
  LMDJ_CHECK(runtime.load(bytes.bytes, bytes.identity) == RuntimeResult::ok);
  RuntimeEpoch epoch;
  LMDJ_CHECK(runtime.start(epoch) == RuntimeResult::ok);
  std::array<RuntimeReceipt, 1> receipt;
  for (std::uint32_t sequence = 1; sequence <= 1100; ++sequence) {
    LMDJ_CHECK(runtime.submit({epoch, sequence, RuntimeCommandKind::stop_all}) == RuntimeResult::accepted);
    float left{}, right{};
    runtime.render(&left, &right, 1);
    LMDJ_CHECK(left == 0 && right == 0);
    LMDJ_CHECK(runtime.poll(receipt) == 1);
    LMDJ_CHECK(receipt[0].sequence == sequence && receipt[0].epoch == epoch);
    LMDJ_CHECK(receipt[0].outcome == RuntimeCommandOutcome::applied);
  }
}

void start_allocation_failure_preserves_epoch_budget() {
  auto limits = config(); limits.maximum_epoch = 1;
  RuntimeFacade runtime(limits);
  const auto bytes = content();
  LMDJ_CHECK(runtime.load(bytes.bytes, bytes.identity) == RuntimeResult::ok);
  RuntimeEpoch epoch;
  allocation_count = 0; fail_at = 1; count_allocations = true;
  const auto result = runtime.start(epoch);
  count_allocations = false; fail_at = 0;
  LMDJ_CHECK(result == RuntimeResult::allocation_failed);
  LMDJ_CHECK(runtime.phase() == RuntimePhase::ready && epoch == RuntimeEpoch{});
  Output output; output.render(runtime); LMDJ_CHECK(output.silent());
  LMDJ_CHECK(runtime.start(epoch) == RuntimeResult::ok);
  output.render(runtime); LMDJ_CHECK(!output.silent());
  runtime.stop();
  LMDJ_CHECK(runtime.start(epoch) == RuntimeResult::epoch_exhausted);
}

void pad_release_and_stop_slot_have_far_side_silence() {
  auto source = snapshot(false);
  source.pads[0].playback.trigger_mode = domain::TriggerMode::loop_gate;
  auto encoded = cooker::encode_runtime_content(source, config().content_limits);
  LMDJ_CHECK(encoded.has_value());
  RuntimeFacade runtime(config());
  LMDJ_CHECK(runtime.load(encoded.value().bytes, encoded.value().identity) == RuntimeResult::ok);
  RuntimeEpoch epoch;
  LMDJ_CHECK(runtime.start(epoch) == RuntimeResult::ok);
  LMDJ_CHECK(runtime.load(encoded.value().bytes, encoded.value().identity) == RuntimeResult::wrong_state);
  LMDJ_CHECK(runtime.start(epoch) == RuntimeResult::wrong_state);
  LMDJ_CHECK(runtime.submit({epoch, 1, RuntimeCommandKind::press, 0, 0}) == RuntimeResult::invalid_command);
  LMDJ_CHECK(runtime.submit({epoch, 1, static_cast<RuntimeCommandKind>(255)}) == RuntimeResult::invalid_command);
  LMDJ_CHECK(runtime.submit({epoch, 1}) == RuntimeResult::accepted);
  Output output; output.render(runtime); LMDJ_CHECK(!output.silent());
  LMDJ_CHECK(runtime.submit({epoch, 2, RuntimeCommandKind::release}) == RuntimeResult::accepted);
  output.render(runtime); LMDJ_CHECK(output.left.back() == 0 && output.right.back() == 0);
  std::array<RuntimeReceipt, 1> receipt;
  LMDJ_CHECK(runtime.poll(receipt) == 1 && receipt[0].sequence == 1);
  LMDJ_CHECK(runtime.poll(receipt) == 1 && receipt[0].sequence == 2);
  LMDJ_CHECK(receipt[0].outcome == RuntimeCommandOutcome::applied);
  LMDJ_CHECK(runtime.submit({epoch, 3}) == RuntimeResult::accepted);
  output.render(runtime); LMDJ_CHECK(!output.silent());
  LMDJ_CHECK(runtime.submit({epoch, 4, RuntimeCommandKind::stop_slot}) == RuntimeResult::accepted);
  output.render(runtime); LMDJ_CHECK(output.left.back() == 0 && output.right.back() == 0);
  LMDJ_CHECK(runtime.poll(receipt) == 1 && receipt[0].sequence == 3);
  LMDJ_CHECK(runtime.poll(receipt) == 1 && receipt[0].sequence == 4);
  LMDJ_CHECK(receipt[0].outcome == RuntimeCommandOutcome::applied);
  LMDJ_CHECK(runtime.poll({}) == 0);
  runtime.render(nullptr, output.right.data(), output.right.size());
  runtime.render(output.left.data(), nullptr, output.left.size());
  runtime.render(output.left.data(), output.right.data(), 0);
}
}  // namespace

void* operator new(std::size_t bytes) { return allocate(bytes); }
void* operator new[](std::size_t bytes) { return allocate(bytes); }
void* operator new(std::size_t bytes, std::align_val_t alignment) {
  return allocate_aligned(bytes, static_cast<std::size_t>(alignment));
}
void* operator new[](std::size_t bytes, std::align_val_t alignment) {
  return allocate_aligned(bytes, static_cast<std::size_t>(alignment));
}
void operator delete(void* pointer) noexcept {
  if (forbid_allocation) std::abort();
  if (pointer) --live_allocations;
  std::free(pointer);
}
void operator delete[](void* pointer) noexcept { operator delete(pointer); }
void operator delete(void* pointer, std::size_t) noexcept { operator delete(pointer); }
void operator delete[](void* pointer, std::size_t) noexcept { operator delete(pointer); }
void operator delete(void* pointer, std::align_val_t) noexcept { operator delete(pointer); }
void operator delete[](void* pointer, std::align_val_t) noexcept { operator delete(pointer); }
void operator delete(void* pointer, std::size_t, std::align_val_t) noexcept { operator delete(pointer); }
void operator delete[](void* pointer, std::size_t, std::align_val_t) noexcept { operator delete(pointer); }

int main() {
  content_summary_preserves_all_canonical_slots_and_modes();
  content_summary_tracks_publication_and_clearing();
  allocator_controls_cover_ordinary_and_aligned_storage();
  fixed_budget_tracks_pending_admission();
  shared_pcm_load_has_one_payload_and_no_float_allocation();
  load_allocates_fixed_storage_before_pcm();
  load_uses_and_accounts_for_the_receipt_bounded_storage();
  for (const std::uint32_t pending : {1U, 128U, 1024U}) {
    old_voice_terminals_and_full_pending_batch_preserve_receipts(pending);
    every_load_allocation_failure_stays_empty(pending);
  }
  lifecycle_journey();
  receipts_and_retry();
  budget_and_allocation_retry();
  counters_and_receipt_retention();
  canonical_preparation_rejects_duplicate_order();
  voice_refusal_is_not_a_started_receipt();
  muted_apply_is_not_a_started_receipt();
  receipt_ring_wrap_preserves_order();
  start_allocation_failure_preserves_epoch_budget();
  pad_release_and_stop_slot_have_far_side_silence();
}
