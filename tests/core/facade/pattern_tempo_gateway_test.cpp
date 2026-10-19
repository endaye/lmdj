#include <algorithm>
#include <array>
#include <atomic>
#include <cstdint>
#include <iostream>
#include <memory>
#include <string_view>
#include <thread>
#include <utility>
#include <vector>

#include <lmdj/facade/pattern_tempo_gateway.hpp>

#include "tests/core/support/test.hpp"

namespace {
using namespace lmdj;
using audio::PatternPublishResult;
using audio::PreparedPatternView;
using audio::RealtimeEngine;
using audio::TransportAnchor;
using cooker::RuntimeSnapshot;
using facade::PatternTempoAuthority;

constexpr const char* kProject = "11111111-1111-4111-8111-111111111111";
constexpr const char* kPattern = "22222222-2222-4222-8222-222222222222";

RuntimeSnapshot snapshot(std::uint16_t bpm = 120, std::uint32_t frames = 12'000) {
  auto pcm = std::make_shared<const cooker::PcmSample>(cooker::PcmSample{
      48'000, 1, std::vector<std::int16_t>(frames, 10'000)});
  const cooker::ResolvedPlayback playback{0, frames, domain::TriggerMode::one_shot, 1.0F, false};
  const cooker::ResolvedPad pad{{0, 0},
      {std::string(64, 'a'), "audio/wav", 44U + 2U * frames}, pcm, playback};
  RuntimeSnapshot result{foundation::ProjectId{kProject}, foundation::PatternId{kPattern},
      1, bpm, 1, 960, 3840, {pad}, {}};
  for (std::uint32_t tick = 0; tick < 3840; tick += 960)
    result.events.push_back({{0, 0}, tick, 1, 127, pcm});
  return result;
}

PreparedPatternView prepare(const RuntimeSnapshot& value) {
  auto prepared = PreparedPatternView::from_snapshot(value);
  LMDJ_CHECK(prepared.has_value());
  return std::move(prepared.value());
}

void render(RealtimeEngine& engine, std::uint64_t frames) {
  std::array<float, 128> left{}, right{};
  while (frames != 0) {
    const auto count = static_cast<std::uint32_t>(std::min<std::uint64_t>(128, frames));
    engine.render(left.data(), right.data(), count);
    frames -= count;
  }
}

void until(RealtimeEngine& engine, std::uint64_t frame) {
  const auto current = engine.telemetry().rendered_frames;
  LMDJ_CHECK(current <= frame);
  render(engine, frame - current);
}

void onset(RealtimeEngine& engine, std::uint64_t frame, std::uint64_t previous) {
  until(engine, frame);
  LMDJ_CHECK(engine.telemetry().started_voices == previous);
  float left{}, right{};
  engine.render(&left, &right, 1);
  LMDJ_CHECK(engine.telemetry().started_voices == previous + 1);
  LMDJ_CHECK(left == 0 && right == 0);
  engine.render(&left, &right, 1);
  LMDJ_CHECK(left > 0 && left == right);
}

struct Fixture {
  RuntimeSnapshot truth;
  PreparedPatternView source;
  RealtimeEngine engine;
  facade::PatternTempoPublicationGateway gateway;
  std::uint64_t generation{};

  explicit Fixture(RuntimeSnapshot initial = snapshot())
      : truth(std::move(initial)), source(prepare(truth)),
        gateway(facade::make_engine_pattern_tempo_publication_gateway(engine)) {
    LMDJ_CHECK(engine.enable_pattern_transport(7).has_value());
    LMDJ_CHECK(engine.publish_sample_bank(audio::PreparedSampleBank::empty(
        foundation::ProjectId{kProject}, 1)) == audio::PublishResult::accepted);
    auto initial_view = source.with_tempo(source.bpm());
    LMDJ_CHECK(initial_view.has_value());
    const auto publication = engine.publish_pattern_view(std::move(initial_view.value()));
    LMDJ_CHECK(publication.result == PatternPublishResult::accepted);
    generation = publication.generation;
    LMDJ_CHECK(engine.start().has_value());
    LMDJ_CHECK(engine.submit_pattern_transport({7, 1, generation,
        audio::PatternTransportAction::start, {}}) == audio::PatternTransportSubmit::accepted);
    render(engine, 1);
    LMDJ_CHECK(engine.inspect_pattern_transport_receipt(7, 1).has_value());
    LMDJ_CHECK(engine.acknowledge_pattern_transport_receipt(7, 1));
  }
  ~Fixture() { engine.stop(); }
  PatternTempoAuthority authority() const { return {engine.telemetry().start_epoch, generation}; }
};

void actual_onset_and_applied_clock_are_not_admission() {
  Fixture f;
  until(f.engine, 12'001);
  const auto admitted = f.gateway.publish(f.source, 240, f.authority());
  LMDJ_CHECK(admitted.has_value());
  const PatternTempoAuthority fast{1, admitted.value().generation};
  LMDJ_CHECK(!f.gateway.observe(fast));
  onset(f.engine, 18'001, 1);
  const auto applied = f.gateway.observe(fast);
  LMDJ_CHECK(applied && applied->playing && applied->applied_frame == 12'001);
  LMDJ_CHECK(applied->anchor == (TransportAnchor{12'001, 1'382'515'200, 240}));
  LMDJ_CHECK(!f.gateway.observe(f.authority()));
  LMDJ_CHECK(f.source.bpm() == 120 && f.truth.bpm == 120 && f.truth.project_revision == 1);
}

void cancel_retains_fractional_position_and_next_loop() {
  Fixture f;
  until(f.engine, 12'001);
  const auto fast = f.gateway.publish(f.source, 240, f.authority());
  LMDJ_CHECK(fast.has_value());
  until(f.engine, 20'000);
  const auto cancel = f.gateway.publish(f.source, 120, {1, fast.value().generation});
  LMDJ_CHECK(cancel.has_value());
  const PatternTempoAuthority restored{1, cancel.value().generation};
  LMDJ_CHECK(!f.gateway.observe(restored));
  onset(f.engine, 40'001, 2);
  LMDJ_CHECK(f.gateway.observe(restored)->anchor ==
      (TransportAnchor{20'000, 3'225'484'800, 120}));
  onset(f.engine, 64'001, 3);
  onset(f.engine, 88'001, 4);
  LMDJ_CHECK(f.engine.current_pattern_origin_frame() == 0);
}

void committed_revision_adoption_never_reverts_tempo() {
  Fixture f;
  until(f.engine, 12'001);
  const auto fast = f.gateway.publish(f.source, 240, f.authority());
  LMDJ_CHECK(fast.has_value());
  until(f.engine, 20'000);
  auto committed = f.truth;
  committed.bpm = 240;
  committed.project_revision = 2;
  auto view = prepare(committed);
  const auto adopted = f.gateway.adopt(std::move(view), {1, fast.value().generation});
  LMDJ_CHECK(adopted.has_value());
  const PatternTempoAuthority next{1, adopted.value().generation};
  LMDJ_CHECK(!f.gateway.observe(next));
  onset(f.engine, 30'001, 2);
  const auto applied = f.gateway.observe(next);
  LMDJ_CHECK(applied && applied->applied_frame == 20'000);
  // Same-BPM adoption retains the existing anchor, including its original
  // frame. It does not synthesize a new anchor at the revision's apply point.
  LMDJ_CHECK(applied->anchor == (TransportAnchor{12'001, 1'382'515'200, 240}));
  onset(f.engine, 42'001, 3);
  const auto old_revision = f.gateway.publish(f.source, 160, next);
  LMDJ_CHECK(!old_revision.has_value());
  LMDJ_CHECK(old_revision.error().details.at("reason") == "tempo_publication_phase_mismatch");
}

void adoption_refusal_does_not_consume_the_view() {
  Fixture f;
  const auto fast = f.gateway.publish(f.source, 240, f.authority());
  LMDJ_CHECK(fast.has_value());
  render(f.engine, 128);
  auto old_tempo = f.truth;
  old_tempo.project_revision = 2;
  auto view = prepare(old_tempo);
  const auto refused = f.gateway.adopt(std::move(view), {1, fast.value().generation});
  LMDJ_CHECK(!refused.has_value());
  LMDJ_CHECK(refused.error().details.at("reason") == "tempo_publication_phase_mismatch");
  LMDJ_CHECK(view.bpm() == 120 && view.project_revision() == 2);
  LMDJ_CHECK(view.pattern_id() == foundation::PatternId{kPattern});
  LMDJ_CHECK(f.gateway.observe({1, fast.value().generation})->anchor.bpm == 240);
}

void pending_and_stale_refusals_keep_the_original_publication() {
  Fixture f;
  const auto first = f.gateway.publish(f.source, 240, f.authority());
  LMDJ_CHECK(first.has_value());
  const auto refused = f.gateway.publish(f.source, 180, f.authority());
  LMDJ_CHECK(!refused.has_value());
  LMDJ_CHECK(refused.error().details.at("reason") == "tempo_publication_pending");
  LMDJ_CHECK(f.engine.pattern_telemetry().pending_publications == 1);
  LMDJ_CHECK(!f.gateway.observe({1, first.value().generation}));
  render(f.engine, 128);
  LMDJ_CHECK(f.gateway.observe({1, first.value().generation})->anchor.bpm == 240);
  const auto stale = f.gateway.publish(f.source, 180, f.authority());
  LMDJ_CHECK(!stale.has_value());
  LMDJ_CHECK(stale.error().details.at("reason") == "tempo_source_stale");
  const auto next = f.gateway.publish(f.source, 180, {1, first.value().generation});
  LMDJ_CHECK(next.has_value() && next.value().generation == first.value().generation + 1);
}

void source_material_and_invalid_bpm_refuse_without_publication() {
  Fixture f;
  const auto before = f.engine.pattern_telemetry().accepted_publications;
  auto recooked = prepare(snapshot()); // Same values/hash/IDs, different PCM owner.
  const auto wrong_material = f.gateway.publish(recooked, 240, f.authority());
  LMDJ_CHECK(!wrong_material.has_value());
  LMDJ_CHECK(wrong_material.error().details.at("reason") == "tempo_publication_phase_mismatch");
  LMDJ_CHECK(!f.gateway.publish(f.source, 39, f.authority()).has_value());
  LMDJ_CHECK(!f.gateway.publish(f.source, 241, f.authority()).has_value());
  LMDJ_CHECK(!f.gateway.publish(f.source, 240, {0, f.generation}).has_value());
  LMDJ_CHECK(!f.gateway.publish(f.source, 240, {1, f.generation + 100}).has_value());
  LMDJ_CHECK(f.engine.pattern_telemetry().accepted_publications == before);
  LMDJ_CHECK(f.gateway.observe(f.authority())->anchor.bpm == 120);
}

void stopped_and_restarted_epochs_cannot_reuse_authority() {
  Fixture f;
  const auto original = f.authority();
  f.engine.stop();
  LMDJ_CHECK(!f.gateway.observe(original));
  LMDJ_CHECK(!f.gateway.publish(f.source, 240, original).has_value());
  auto view = prepare(f.truth);
  LMDJ_CHECK(!f.gateway.adopt(std::move(view), original).has_value());
  LMDJ_CHECK(view.project_revision() == 1);
  LMDJ_CHECK(f.engine.start().has_value());
  LMDJ_CHECK(f.engine.telemetry().start_epoch == 2);
  LMDJ_CHECK(!f.gateway.observe(original)); // Also before first new render.
  LMDJ_CHECK(!f.gateway.publish(f.source, 240, original).has_value());
  render(f.engine, 128);
  LMDJ_CHECK(!f.gateway.observe(original));
}

void held_one_shot_keeps_its_voice_across_preview() {
  auto value = snapshot(120, 96'000);
  value.events.resize(1);
  Fixture f(std::move(value));
  until(f.engine, 12'000);
  float before{}, right{};
  f.engine.render(&before, &right, 1);
  LMDJ_CHECK(before > 0 && f.engine.telemetry().active_voices == 1);
  const auto preview = f.gateway.publish(f.source, 240, f.authority());
  LMDJ_CHECK(preview.has_value());
  float after{};
  f.engine.render(&after, &right, 1);
  LMDJ_CHECK(after == before && right == after);
  LMDJ_CHECK(f.engine.telemetry().started_voices == 1 && f.engine.telemetry().active_voices == 1);
}

void fractional_tempo_uses_exact_native_anchor() {
  Fixture f(snapshot(97));
  until(f.engine, 12'001);
  const auto preview = f.gateway.publish(f.source, 240, f.authority());
  LMDJ_CHECK(preview.has_value());
  onset(f.engine, 19'151, 1);
  LMDJ_CHECK(f.gateway.observe({1, preview.value().generation})->anchor ==
      (TransportAnchor{12'001, 1'117'533'120, 240}));
}

void full_uint64_numerator_is_forwarded_without_rounding() {
  auto value = snapshot(97);
  value.events.clear();
  Fixture f(std::move(value));
  const auto continuous = f.gateway.publish(f.source, 97, f.authority());
  LMDJ_CHECK(continuous.has_value());
  render(f.engine, 1);
  constexpr std::uint64_t frame = (std::uint64_t{1} << 44) + 1;
  constexpr std::uint64_t numerator = frame * 97U * 960U;
  static_assert(numerator > (std::uint64_t{1} << 53) && numerator % 256 == 192);
  f.engine.set_rendered_frames_quiescent_for_testing(frame);
  const auto next = f.gateway.publish(f.source, 240, {1, continuous.value().generation});
  LMDJ_CHECK(next.has_value());
  render(f.engine, 1);
  const auto actual = f.gateway.observe({1, next.value().generation});
  LMDJ_CHECK(actual && actual->applied_frame == frame);
  LMDJ_CHECK(actual->anchor == (TransportAnchor{frame, numerator, 240}));
}

void concurrent_render_publication_and_reclaim() {
  auto value = snapshot();
  value.events.clear();
  Fixture f(std::move(value));
  std::atomic<std::uint64_t> callbacks{};
  std::jthread audio_thread([&](std::stop_token stop) {
    std::array<float, 128> left{}, right{};
    while (!stop.stop_requested()) {
      f.engine.render(left.data(), right.data(), 128);
      callbacks.fetch_add(1, std::memory_order_release);
    }
  });
  auto authority = f.authority();
  std::uint64_t accepted{}, refused{};
  constexpr std::uint64_t rounds = 256;
  for (std::uint64_t round = 0; round < rounds; ++round) {
    bool applied = false;
    for (std::uint32_t probe = 0; probe < 100'000; ++probe) {
      if (f.gateway.observe(authority)) {
        applied = true;
        break;
      }
      std::this_thread::yield();
    }
    LMDJ_CHECK(applied);
    const auto next = f.gateway.publish(f.source, round % 2 == 0 ? 240 : 120, authority);
    LMDJ_CHECK(next.has_value());
    ++accepted;
    // Whether audio already applied or still owns pending material, the old
    // authority cannot admit another detent. Both are real refusal outcomes.
    const auto old = f.gateway.publish(f.source, 180, authority);
    LMDJ_CHECK(!old.has_value());
    ++refused;
    LMDJ_CHECK(old.error().details.at("reason") == "tempo_source_stale" ||
        old.error().details.at("reason") == "tempo_publication_pending" ||
        old.error().details.at("reason") == "tempo_publication_phase_mismatch");
    authority.generation = next.value().generation;
    static_cast<void>(f.engine.reclaim_retired_patterns());
  }
  audio_thread.request_stop();
  audio_thread.join();
  render(f.engine, 128);
  LMDJ_CHECK(f.gateway.observe(authority).has_value());
  LMDJ_CHECK(accepted == rounds && refused == rounds && callbacks.load() > 0);
  LMDJ_CHECK(f.source.bpm() == 120 && f.truth.project_revision == 1);
  std::cout << "tempo gateway race: accepted=" << accepted << " refused=" << refused
            << " callbacks=" << callbacks.load() << '\n';
}
}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc == 2 && std::string_view(argv[1]) == "--stress") {
      concurrent_render_publication_and_reclaim();
      return 0;
    }
    LMDJ_CHECK(argc == 1);
    actual_onset_and_applied_clock_are_not_admission();
    cancel_retains_fractional_position_and_next_loop();
    committed_revision_adoption_never_reverts_tempo();
    adoption_refusal_does_not_consume_the_view();
    pending_and_stale_refusals_keep_the_original_publication();
    source_material_and_invalid_bpm_refuse_without_publication();
    stopped_and_restarted_epochs_cannot_reuse_authority();
    held_one_shot_keeps_its_voice_across_preview();
    fractional_tempo_uses_exact_native_anchor();
    full_uint64_numerator_is_forwarded_without_rounding();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  return 0;
}
