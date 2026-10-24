#include "pattern_transport_opfs_probe.hpp"

#if !defined(__EMSCRIPTEN__) || !defined(LMDJ_WEB_AUDIO_CONFORMANCE)
#error "why: OPFS probe is conformance-only; remedy: exclude it from production targets"
#endif

#include <emscripten/emscripten.h>
#include <array>
#include <lmdj/audio/realtime_engine.hpp>
#include <lmdj/project_io/storage_platform.hpp>
#include <lmdj/facade/pattern_transport_io_testing.hpp>

#if !defined(LMDJ_PATTERN_TRANSPORT_TESTING) || !LMDJ_PATTERN_TRANSPORT_TESTING
#error "why: production-owner OPFS witness needs its conformance-only Facade hook"
#endif

namespace lmdj::web_runtime::test {
namespace {
constexpr auto transport_probe_root = "/lmdj-workspace/transport-executor-proof";
constexpr auto transport_probe_file = "/lmdj-workspace/transport-executor-proof/receipt";
constexpr auto transport_probe_bytes = kTransportProbeBytes;

// Separate from T0's isolated executor below: this latches the actual normal
// controller factory's immutable open/admit work on its existing I/O worker.
// States: idle0, open-armed1, admit-armed2, installed3, open-held4,
// admit-held5, write-flushed6, failed7, owner-work-succeeded8,
// segment-armed9, segment-admission-switch-held10.
std::atomic<std::uint32_t> controller_gate_state{0};
std::atomic<std::uint32_t> controller_gate_release{0};
// The hook also observes unrelated owners. Only the worker that claimed the
// selected work may publish its completion or remove its worker-local wrapper.
thread_local bool controller_gate_work_claimed{};
thread_local bool controller_segment_worker{};
// Read-only copies of this selected worker's actual press-admit work. Publish
// each complete row after its fields; never change the request or its result.
std::array<std::array<std::atomic<std::uint64_t>, 7>, 16> segment_inputs{};
std::atomic<unsigned> segment_input_count{0};
std::atomic<std::uint64_t> segment_runtime_generation{0}, segment_transport_epoch{0};
// Written/read only on serialized control, separately from the I/O worker.
std::string segment_cutoff_json;

EM_JS(void, install_controller_io_pause,
      (void* state, void* release, unsigned held_state), {
  if (LmdjOpfs.lmdjControllerGateOriginal || LmdjOpfs.lmdjControllerFlushOriginal ||
      LmdjOpfs.lmdjControllerAppendOriginal)
    throw new Error("controller I/O gate already installed");
  if (held_state === 10) {
    // Segment replay may sync the already-written preparation first. Select
    // the actual new switch record, then hold its real flush after its write.
    const originalAppend = LmdjOpfs.appendDurable;
    LmdjOpfs.lmdjControllerAppendOriginal = originalAppend;
    LmdjOpfs.appendDurable = async function(...args) {
      let selected = false;
      if (args[4] > 0) {
        try {
          const record = JSON.parse(new TextDecoder().decode(this.bytes(args[3], args[4])));
          selected = record.payload?.kind === "admission-switch";
        } catch (_) { /* Observation must not change an original append error. */ }
      }
      if (selected) {
        LmdjOpfs.appendDurable = originalAppend;
        delete LmdjOpfs.lmdjControllerAppendOriginal;
        const prototype = FileSystemSyncAccessHandle.prototype;
        const originalFlush = prototype.flush;
        LmdjOpfs.lmdjControllerFlushOriginal = originalFlush;
        prototype.flush = function(...arguments_) {
          prototype.flush = originalFlush;
          delete LmdjOpfs.lmdjControllerFlushOriginal;
          Atomics.store(HEAPU32, state >>> 2, held_state);
          while (Atomics.load(HEAPU32, release >>> 2) === 0)
            Atomics.wait(HEAP32, release >>> 2, 0, 2);
          const result = originalFlush.apply(this, arguments_);
          Atomics.store(HEAPU32, state >>> 2, 6);
          return result;
        };
      }
      return originalAppend.apply(this, args);
    };
    return;
  }
  if (held_state === 5) {
    // appendDurable uses the real sync handle directly rather than
    // writeSyncComplete. Pause only this I/O worker's next actual flush after
    // its append write; the main/control/audio owners remain runnable.
    const prototype = FileSystemSyncAccessHandle.prototype;
    const originalFlush = prototype.flush;
    LmdjOpfs.lmdjControllerFlushOriginal = originalFlush;
    prototype.flush = function(...arguments_) {
      prototype.flush = originalFlush;
      delete LmdjOpfs.lmdjControllerFlushOriginal;
      Atomics.store(HEAPU32, state >>> 2, held_state);
      while (Atomics.load(HEAPU32, release >>> 2) === 0)
        Atomics.wait(HEAP32, release >>> 2, 0, 2);
      const result = originalFlush.apply(this, arguments_);
      Atomics.store(HEAPU32, state >>> 2, 6);
      return result;
    };
    return;
  }
  const original = LmdjOpfs.writeSyncComplete;
  LmdjOpfs.lmdjControllerGateOriginal = original;
  LmdjOpfs.writeSyncComplete = async function(file, bytes, observer, operation, fault) {
    // Journal begin first writes a real ownership intent. Retain that
    // unchanged path, then hold the actual immutable Journal write.
    if (operation !== "immutable")
      return original.call(this, file, bytes, observer, operation, fault);
    LmdjOpfs.writeSyncComplete = original;
    delete LmdjOpfs.lmdjControllerGateOriginal;
    if (observer) throw new Error("unexpected production owner write observer");
    const held = {
      writeChunkSize: (_operation, remaining) => remaining,
      async afterWrite() {
        Atomics.store(HEAPU32, state >>> 2, held_state);
        while (Atomics.load(HEAPU32, release >>> 2) === 0)
          await new Promise(resolve => setTimeout(resolve, 2));
      },
      async stopAtFault() {},
      afterFlush() { Atomics.store(HEAPU32, state >>> 2, 6); },
    };
    return original.call(this, file, bytes, held, operation, fault);
  };
});

EM_JS(void, clear_unentered_controller_io_pause, (), {
  if (LmdjOpfs.lmdjControllerGateOriginal) {
    LmdjOpfs.writeSyncComplete = LmdjOpfs.lmdjControllerGateOriginal;
    delete LmdjOpfs.lmdjControllerGateOriginal;
  }
  if (LmdjOpfs.lmdjControllerAppendOriginal) {
    LmdjOpfs.appendDurable = LmdjOpfs.lmdjControllerAppendOriginal;
    delete LmdjOpfs.lmdjControllerAppendOriginal;
  }
  if (LmdjOpfs.lmdjControllerFlushOriginal) {
    FileSystemSyncAccessHandle.prototype.flush = LmdjOpfs.lmdjControllerFlushOriginal;
    delete LmdjOpfs.lmdjControllerFlushOriginal;
  }
});

void before_controller_work(void*, const facade::PatternTransportWorkRequest& work) noexcept {
  try {
    const auto payload = nlohmann::json::parse(work.payload);
    const auto op = payload.at("op").get<std::string>();
    if (controller_segment_worker && op == "admit" &&
        payload.at("candidate").at("pressed").get<bool>()) {
      const auto index = segment_input_count.load(std::memory_order_relaxed);
      if (index < segment_inputs.size()) {
        const auto& c = payload.at("candidate");
        const std::array<std::uint64_t, 7> values{c.at("frame"), c.at("correlation"),
            c.at("bank"), c.at("pad"), work.identity.runtime_generation,
            work.identity.transport_epoch, c.at("watermark")};
        for (unsigned field = 0; field != values.size(); ++field)
          segment_inputs[index][field].store(values[field], std::memory_order_relaxed);
        segment_input_count.store(index + 1, std::memory_order_release);
      }
    }
    auto expected = controller_gate_state.load(std::memory_order_acquire);
    if (expected != 1 && expected != 2 && expected != 9) return;
    if (op != (expected == 1 ? "open" : expected == 2 ? "admit" : "segment")) return;
    const auto held = expected == 1 ? 4U : expected == 2 ? 5U : 10U;
    if (!controller_gate_state.compare_exchange_strong(expected, 3,
          std::memory_order_acq_rel, std::memory_order_acquire)) return;
    controller_gate_work_claimed = true;
    controller_segment_worker = held == 10;
    if (controller_segment_worker) {
      segment_runtime_generation.store(work.identity.runtime_generation, std::memory_order_release);
      segment_transport_epoch.store(work.identity.transport_epoch, std::memory_order_release);
    }
    install_controller_io_pause(&controller_gate_state, &controller_gate_release, held);
  } catch (...) {
    controller_gate_state.store(7, std::memory_order_release);
  }
}

void after_controller_work(void*, const facade::PatternTransportWorkRequest&,
    const facade::PatternTransportWorkCompletion* completion) noexcept {
  if (!controller_gate_work_claimed) return;
  controller_gate_work_claimed = false;
  clear_unentered_controller_io_pause();
  const auto wrote = controller_gate_state.load(std::memory_order_acquire) == 6;
  controller_gate_state.store(wrote && completion &&
      completion->outcome == facade::PatternTransportWorkOutcome::success ? 8 : 7,
      std::memory_order_release);
}

void observe_closing_receipt(void*, const audio::PatternTransportReceipt& receipt) noexcept {
  const auto epoch = segment_transport_epoch.load(std::memory_order_acquire);
  if (!epoch || epoch == UINT64_MAX || receipt.epoch != epoch + 1 ||
      receipt.runtime_generation != segment_runtime_generation.load(std::memory_order_acquire)) return;
  try {
    segment_cutoff_json = nlohmann::json{{"runtime_generation", receipt.runtime_generation},
        {"epoch", receipt.epoch}, {"effective_frame", receipt.effective_frame},
        {"origin_frame", receipt.origin_frame}, {"pattern_generation", receipt.pattern_generation},
        {"pattern_id", receipt.pattern_id.value()}, {"bpm", receipt.bpm}, {"playing", receipt.playing}}.dump();
  } catch (...) { controller_gate_state.store(7, std::memory_order_release); }
}

const facade::testing::PatternTransportIoWorkHook controller_work_hook{
    nullptr, &before_controller_work, &after_controller_work, &observe_closing_receipt};

EM_JS(void, install_transport_probe_pause, (void* reached, void* release), {
  const original = LmdjOpfs.writeSyncComplete;
  LmdjOpfs.writeSyncComplete = async function(file, bytes, observer, operation, fault) {
    LmdjOpfs.writeSyncComplete = original;
    const held = {
      writeChunkSize: (_operation, remaining) => remaining,
      async afterWrite() {
        Atomics.store(HEAPU32, reached >>> 2, 1);
        while (Atomics.load(HEAPU32, release >>> 2) === 0)
          await new Promise(resolve => setTimeout(resolve, 2));
      },
      async stopAtFault() {},
      afterFlush() {},
    };
    return original.call(this, file, bytes, held, operation, fault);
  };
});

class TransportOpfsProbeOwner final : public lmdj::facade::PatternTransportWorkOwner {
 public:
  TransportOpfsProbeOwner(std::atomic<std::uint32_t>& reached,
                          std::atomic<std::uint32_t>& release)
      : reached_(reached), release_(release),
        storage_(lmdj::project_io::make_default_project_storage_platform()) {}
  lmdj::facade::PatternTransportWorkCompletion execute(
      const lmdj::facade::PatternTransportWorkRequest& work) override {
    using lmdj::facade::PatternTransportWorkOutcome;
    auto acquired = storage_->acquire_writer(transport_probe_root);
    if (!acquired.has_value())
      return {PatternTransportWorkOutcome::refused, {}, acquired.error()};
    lease_ = std::move(acquired.value());
    if (work.payload == "prepare") {
      const auto directory = storage_->ensure_directory(transport_probe_root);
      if (!directory.has_value())
        return {PatternTransportWorkOutcome::refused, {}, directory.error()};
      // Hold the actual create_immutable Asyncify invocation after a sync write,
      // before flush, while its file handle and Project writer lease are owned.
      // This hook exists only in the conformance link and on this worker.
      install_transport_probe_pause(&reached_, &release_);
      const std::string_view payload{transport_probe_bytes};
      const auto written = storage_->create_immutable(
          transport_probe_file, std::as_bytes(std::span{payload.data(), payload.size()}));
      if (!written.has_value())
        return {PatternTransportWorkOutcome::unknown, {}, written.error()};
    }
    const auto read = storage_->read_complete(transport_probe_file);
    if (!read.has_value())
      return {PatternTransportWorkOutcome::unknown, {}, read.error()};
    return {PatternTransportWorkOutcome::success,
            std::string(reinterpret_cast<const char*>(read.value().data()), read.value().size()),
            std::nullopt};
  }
 private:
  std::atomic<std::uint32_t>& reached_;
  std::atomic<std::uint32_t>& release_;
  std::shared_ptr<lmdj::project_io::ProjectStoragePlatform> storage_;
  // Destroyed before storage_ and on the same worker that acquired it.
  std::unique_ptr<lmdj::project_io::ProjectWriterLease> lease_;
};

}  // namespace

int pattern_controller_io_gate(unsigned action) noexcept {
  if (action == 0) return static_cast<int>(controller_gate_state.load(std::memory_order_acquire));
  if (action == 3) {
    controller_gate_release.store(1, std::memory_order_release);
    return 1;
  }
  if (action != 1 && action != 2 && action != 4) return -1;
  auto expected = controller_gate_state.load(std::memory_order_acquire);
  if (expected != 0 && expected != 8) return -1;
  // Tests configure from one browser owner. Refuse to rearm any held/unknown
  // work; the release action never implies native or durable completion.
  controller_gate_release.store(0, std::memory_order_release);
  if (action == 4) {
    segment_input_count.store(0, std::memory_order_release);
    segment_runtime_generation.store(0, std::memory_order_release);
    segment_transport_epoch.store(0, std::memory_order_release);
    segment_cutoff_json.clear();
  }
  if (!controller_gate_state.compare_exchange_strong(expected, action == 4 ? 9U : action,
        std::memory_order_acq_rel, std::memory_order_acquire)) return -1;
  facade::testing::install_pattern_transport_io_work_hook_for_testing(&controller_work_hook);
  return 1;
}

double pattern_controller_io_input(unsigned index, unsigned field) noexcept {
  const auto count = segment_input_count.load(std::memory_order_acquire);
  if (field == 7) return count;
  if (index >= count || index >= segment_inputs.size() || field >= 7) return -1;
  const auto value = segment_inputs[index][field].load(std::memory_order_relaxed);
  if (value > 9007199254740991ULL) return -2;
  return static_cast<double>(value);
}

const char* pattern_controller_io_cutoff() noexcept {
  return segment_cutoff_json.empty() ? nullptr : segment_cutoff_json.c_str();
}

std::unique_ptr<facade::PatternTransportWorkOwner> make_transport_opfs_probe_owner(
    std::atomic<std::uint32_t>& reached, std::atomic<std::uint32_t>& release) {
  return std::make_unique<TransportOpfsProbeOwner>(reached, release);
}
}  // namespace lmdj::web_runtime::test

extern "C" EMSCRIPTEN_KEEPALIVE int lmdj_web_audio_test_pattern_controller_io_gate(
    unsigned action) noexcept {
  return lmdj::web_runtime::test::pattern_controller_io_gate(action);
}

extern "C" EMSCRIPTEN_KEEPALIVE double lmdj_web_audio_test_pattern_controller_io_input(
    unsigned index, unsigned field) noexcept {
  return lmdj::web_runtime::test::pattern_controller_io_input(index, field);
}

extern "C" EMSCRIPTEN_KEEPALIVE const char* lmdj_web_audio_test_pattern_controller_io_cutoff() noexcept {
  return lmdj::web_runtime::test::pattern_controller_io_cutoff();
}
