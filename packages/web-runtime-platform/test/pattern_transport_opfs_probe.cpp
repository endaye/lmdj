#include "pattern_transport_opfs_probe.hpp"

#if !defined(__EMSCRIPTEN__) || !defined(LMDJ_WEB_AUDIO_CONFORMANCE)
#error "why: OPFS probe is conformance-only; remedy: exclude it from production targets"
#endif

#include <emscripten/emscripten.h>
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
// admit-held5, write-flushed6, failed7, owner-work-succeeded8.
std::atomic<std::uint32_t> controller_gate_state{0};
std::atomic<std::uint32_t> controller_gate_release{0};
// The hook also observes unrelated owners. Only the worker that claimed the
// selected work may publish its completion or remove its worker-local wrapper.
thread_local bool controller_gate_work_claimed{};

EM_JS(void, install_controller_io_pause,
      (void* state, void* release, unsigned held_state), {
  if (LmdjOpfs.lmdjControllerGateOriginal || LmdjOpfs.lmdjControllerFlushOriginal)
    throw new Error("controller I/O gate already installed");
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
  if (LmdjOpfs.lmdjControllerFlushOriginal) {
    FileSystemSyncAccessHandle.prototype.flush = LmdjOpfs.lmdjControllerFlushOriginal;
    delete LmdjOpfs.lmdjControllerFlushOriginal;
  }
});

void before_controller_work(void*, const facade::PatternTransportWorkRequest& work) noexcept {
  try {
    auto expected = controller_gate_state.load(std::memory_order_acquire);
    if (expected != 1 && expected != 2) return;
    const auto op = nlohmann::json::parse(work.payload).at("op").get<std::string>();
    if (op != (expected == 1 ? "open" : "admit")) return;
    const auto held = expected == 1 ? 4U : 5U;
    if (!controller_gate_state.compare_exchange_strong(expected, 3,
          std::memory_order_acq_rel, std::memory_order_acquire)) return;
    controller_gate_work_claimed = true;
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

const facade::testing::PatternTransportIoWorkHook controller_work_hook{
    nullptr, &before_controller_work, &after_controller_work};

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
  if (action != 1 && action != 2) return -1;
  auto expected = controller_gate_state.load(std::memory_order_acquire);
  if (expected != 0 && expected != 8) return -1;
  // Tests configure from one browser owner. Refuse to rearm any held/unknown
  // work; the release action never implies native or durable completion.
  controller_gate_release.store(0, std::memory_order_release);
  if (!controller_gate_state.compare_exchange_strong(expected, action,
        std::memory_order_acq_rel, std::memory_order_acquire)) return -1;
  facade::testing::install_pattern_transport_io_work_hook_for_testing(&controller_work_hook);
  return 1;
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
