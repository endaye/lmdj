#include "pattern_transport_opfs_probe.hpp"

#if !defined(__EMSCRIPTEN__) || !defined(LMDJ_WEB_AUDIO_CONFORMANCE)
#error "why: OPFS probe is conformance-only; remedy: exclude it from production targets"
#endif

#include <emscripten/emscripten.h>
#include <lmdj/project_io/storage_platform.hpp>

namespace lmdj::web_runtime::test {
namespace {
constexpr auto transport_probe_root = "/lmdj-workspace/transport-executor-proof";
constexpr auto transport_probe_file = "/lmdj-workspace/transport-executor-proof/receipt";
constexpr auto transport_probe_bytes = kTransportProbeBytes;

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

std::unique_ptr<facade::PatternTransportWorkOwner> make_transport_opfs_probe_owner(
    std::atomic<std::uint32_t>& reached, std::atomic<std::uint32_t>& release) {
  return std::make_unique<TransportOpfsProbeOwner>(reached, release);
}
}  // namespace lmdj::web_runtime::test
