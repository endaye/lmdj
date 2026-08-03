#include <atomic>
#include <cstddef>
#include <cstdint>

#include <emscripten/webaudio.h>

extern std::atomic<std::uint32_t> shared_probe_word;

namespace {

constexpr std::uint32_t kSharedMarkerMask = 1U << 0U;
constexpr std::uint32_t kQuantumMismatchMask = 1U << 1U;
constexpr std::uint32_t kObservedFramesShift = 2U;
constexpr std::uint32_t kObservedFramesMask =
    ~((1U << kObservedFramesShift) - 1U);
constexpr int kRequiredQuantumFrames = 128;
static_assert(std::atomic<std::uint32_t>::is_always_lock_free);

std::uint32_t record_callback_frames(std::atomic<std::uint32_t>& word,
                                     int frames) noexcept {
  const std::uint32_t packed_frames =
      (static_cast<std::uint32_t>(frames) << kObservedFramesShift) &
      kObservedFramesMask;
  std::uint32_t current = word.load(std::memory_order_relaxed);
  while ((current & kQuantumMismatchMask) == 0U) {
    std::uint32_t desired =
        (current & ~kObservedFramesMask) | packed_frames;
    if (frames != kRequiredQuantumFrames) {
      desired |= kQuantumMismatchMask;
    }
    if (word.compare_exchange_strong(current,
                                     desired,
                                     std::memory_order_relaxed,
                                     std::memory_order_relaxed)) {
      return desired;
    }
  }
  return current;
}

#if defined(LMDJ_PROBE_CONTROL)
int observed_callback_frames(std::uint32_t word) noexcept {
  return static_cast<int>((word & kObservedFramesMask) >>
                          kObservedFramesShift);
}
#endif

}  // namespace

#if defined(LMDJ_PROBE_AUDIO_CALLBACK)

extern "C" bool process_probe(int num_inputs,
                              const AudioSampleFrame* inputs,
                              int num_outputs,
                              AudioSampleFrame* outputs,
                              int num_params,
                              const AudioParamFrame* params,
                              void* user_data) {
  const std::uint32_t packed_state = record_callback_frames(
      shared_probe_word, outputs[0].samplesPerChannel);
  outputs[0].data[(outputs[0].numberOfChannels - 1) *
                  outputs[0].samplesPerChannel] =
      (packed_state & kSharedMarkerMask) != 0U ? 1.0F : 0.0F;
  return true;
}

#elif defined(LMDJ_PROBE_CONTROL)

#include <array>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <string_view>
#include <sys/stat.h>
#include <unistd.h>

#include <emscripten.h>
#include <emscripten/em_asm.h>
#include <emscripten/threading.h>
#include <emscripten/wasmfs.h>

extern "C" bool process_probe(int num_inputs,
                              const AudioSampleFrame* inputs,
                              int num_outputs,
                              AudioSampleFrame* outputs,
                              int num_params,
                              const AudioParamFrame* params,
                              void* user_data);

std::atomic<std::uint32_t> shared_probe_word{0};

namespace {

constexpr int kResultCapacity = 8192;
constexpr int kControlProbeCount = 1000;
constexpr std::string_view kWasmFsPayload = "control-pthread-opfs";

std::atomic<int> control_browser_main{-1};
std::atomic<int> control_done{0};
std::atomic<int> control_probes{0};
std::atomic<int> wasmfs_ok{0};
std::atomic<int> audio_state{0};
std::atomic<int> audio_ready{0};
std::atomic<int> configured_channels{0};

alignas(16) std::array<std::uint8_t, 16 * 1024> audio_worklet_stack{};
std::array<char, kResultCapacity> lease_json{};
std::array<char, kResultCapacity> iteration_json{};
std::array<char, kResultCapacity> replacement_json{};

EMSCRIPTEN_WEBAUDIO_T audio_context = 0;
EMSCRIPTEN_WEBAUDIO_T audio_node = 0;

EM_ASYNC_JS(int,
            lmdj_opfs_acquire_writer,
            (char* output, int output_capacity), {
  const copyResult = (value) => {
    const text = JSON.stringify(value);
    if (lengthBytesUTF8(text) + 1 > output_capacity) return false;
    stringToUTF8(text, output, output_capacity);
    return true;
  };
  let first = null;
  try {
    const normalizedPath = "/projects/toolchain-probe.lmdj";
    const digest = new Uint8Array(
      await crypto.subtle.digest("SHA-256", new TextEncoder().encode(normalizedPath)),
    );
    const leaseKey = Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join("");
    const root = await navigator.storage.getDirectory();
    const metadata = await root.getDirectoryHandle(".lmdj-workspace", {create: true});
    const leases = await metadata.getDirectoryHandle("leases", {create: true});
    const file = await leases.getFileHandle(`${leaseKey}.lock`, {create: true});
    const before = await file.getFile();
    const existed = before.size > 0;

    first = await file.createSyncAccessHandle();
    const identity = new TextEncoder().encode(leaseKey);
    if (first.getSize() === 0) {
      const written = first.write(identity, {at: 0});
      if (written !== identity.byteLength) throw new Error("short lease identity write");
      first.flush();
    }
    const stored = new Uint8Array(first.getSize());
    const read = first.read(stored, {at: 0});
    if (read !== stored.byteLength) throw new Error("short lease identity read");
    const storedIdentity = new TextDecoder().decode(stored);

    const startedAt = performance.now();
    let busy = false;
    let busyName = "";
    try {
      const competing = await Promise.race([
        file.createSyncAccessHandle(),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error("lease contention timed out")), 500),
        ),
      ]);
      competing.close();
    } catch (error) {
      if (String(error).includes("timed out")) throw error;
      busyName = error?.name || "DOMException";
      if (busyName !== "NoModificationAllowedError") throw error;
      busy = true;
    }
    const busyElapsedMs = performance.now() - startedAt;
    first.close();
    first = null;

    const reacquired = await file.createSyncAccessHandle();
    const reacquiredBytes = new Uint8Array(reacquired.getSize());
    reacquired.read(reacquiredBytes, {at: 0});
    reacquired.close();
    const reacquiredIdentity = new TextDecoder().decode(reacquiredBytes);

    const result = {
      ok:
        busy &&
        busyElapsedMs < 500 &&
        storedIdentity === leaseKey &&
        reacquiredIdentity === leaseKey,
      code: busy ? "PROJECT_BUSY" : "",
      contentionError: busyName,
      contentionElapsedMs: busyElapsedMs,
      existingIdentity: existed,
      leaseKey,
      normalizedPath,
      reacquired: reacquiredIdentity === leaseKey,
      stableIdentity: storedIdentity === leaseKey,
    };
    return copyResult(result) && result.ok ? 1 : 0;
  } catch (error) {
    if (first) first.close();
    copyResult({ok: false, error: String(error)});
    return 0;
  }
});

EM_ASYNC_JS(int,
            lmdj_opfs_list_names,
            (char* output, int output_capacity), {
  const copyResult = (value) => {
    const text = JSON.stringify(value);
    if (lengthBytesUTF8(text) + 1 > output_capacity) return false;
    stringToUTF8(text, output, output_capacity);
    return true;
  };
  try {
    const root = await navigator.storage.getDirectory();
    const metadata = await root.getDirectoryHandle(".lmdj-workspace", {create: true});
    const directory = await metadata.getDirectoryHandle("iteration", {create: true});
    for await (const [name] of directory.entries()) {
      await directory.removeEntry(name, {recursive: true});
    }
    const source = ["z", "ä", "a", "é", "😀"];
    for (const name of source) {
      await directory.getFileHandle(name, {create: true});
    }
    const collected = [];
    for await (const [name] of directory.entries()) collected.push(name);
    const encoder = new TextEncoder();
    const compareUnsignedUtf8 = (left, right) => {
      const a = encoder.encode(left);
      const b = encoder.encode(right);
      const count = Math.min(a.length, b.length);
      for (let index = 0; index < count; index += 1) {
        if (a[index] !== b[index]) return a[index] - b[index];
      }
      return a.length - b.length;
    };
    const sorted = [...collected].sort(compareUnsignedUtf8);
    const expected = ["a", "z", "ä", "é", "😀"];
    const ok =
      collected.length === source.length &&
      sorted.length === expected.length &&
      sorted.every((name, index) => name === expected[index]);
    const result = {ok, collected, sorted, ordering: "unsigned-utf8"};
    return copyResult(result) && ok ? 1 : 0;
  } catch (error) {
    copyResult({ok: false, error: String(error)});
    return 0;
  }
});

EM_ASYNC_JS(int,
            lmdj_opfs_replace_complete,
            (char* output, int output_capacity), {
  const copyResult = (value) => {
    const text = JSON.stringify(value);
    if (lengthBytesUTF8(text) + 1 > output_capacity) return false;
    stringToUTF8(text, output, output_capacity);
    return true;
  };
  const writeComplete = async (directory, name, value) => {
    const file = await directory.getFileHandle(name, {create: true});
    const writable = await file.createWritable({keepExistingData: false});
    await writable.write(value);
    await writable.close();
  };
  const readText = async (directory, name) => {
    const file = await directory.getFileHandle(name);
    return (await file.getFile()).text();
  };
  const faultPoints = [
    "before_write",
    "during_write",
    "before_close",
    "after_close",
    "before_cleanup",
  ];
  try {
    const root = await navigator.storage.getDirectory();
    const metadata = await root.getDirectoryHandle(".lmdj-workspace", {create: true});
    const directory = await metadata.getDirectoryHandle("replacement", {create: true});
    let marker = "";
    try {
      marker = await readText(directory, "restart-phase.txt");
    } catch (error) {
      if (error?.name !== "NotFoundError") throw error;
    }

    if (marker === "prepared") {
      const recovered = {};
      let ok = true;
      for (const point of faultPoints) {
        const value = await readText(directory, `${point}.txt`);
        recovered[point] = value;
        ok = ok && (value === "old" || value === "new");
      }
      const successfulClose = await readText(directory, "successful_close.txt");
      ok = ok && successfulClose === "new";
      for (const name of [...faultPoints.map((point) => `${point}.txt`), "successful_close.txt", "restart-phase.txt"]) {
        await directory.removeEntry(name);
      }
      const result = {
        ok,
        phase: "recovered",
        faultPoints,
        recovered,
        successfulClose,
      };
      return copyResult(result) && ok ? 1 : 0;
    }

    for await (const [name] of directory.entries()) {
      await directory.removeEntry(name, {recursive: true});
    }
    await writeComplete(directory, "successful_close.txt", "old");
    await writeComplete(directory, "successful_close.txt", "new");
    for (const point of faultPoints) {
      await writeComplete(directory, `${point}.txt`, "old");
    }

    const interruptedStreams = [];
    const duringWrite = await (
      await directory.getFileHandle("during_write.txt")
    ).createWritable({keepExistingData: false});
    await duringWrite.write("n");
    interruptedStreams.push(duringWrite);

    const beforeClose = await (
      await directory.getFileHandle("before_close.txt")
    ).createWritable({keepExistingData: false});
    await beforeClose.write("new");
    interruptedStreams.push(beforeClose);

    await writeComplete(directory, "after_close.txt", "new");
    await writeComplete(directory, "before_cleanup.txt", "new");
    await writeComplete(directory, "restart-phase.txt", "prepared");
    globalThis.lmdjInterruptedReplacementStreams = interruptedStreams;

    const result = {
      ok: true,
      phase: "prepared",
      faultPoints,
      successfulClose: "new",
    };
    return copyResult(result) ? 1 : 0;
  } catch (error) {
    copyResult({ok: false, error: String(error)});
    return 0;
  }
});

bool run_wasmfs_probe() {
  const backend_t backend = wasmfs_create_opfs_backend();
  if (backend == nullptr) {
    return false;
  }
  const int mount_result = wasmfs_create_directory("/opfs", 0777, backend);
  if (mount_result != 0 && errno != EEXIST) {
    return false;
  }
  const char* path = "/opfs/control-pthread.txt";
  const int descriptor = open(path, O_CREAT | O_TRUNC | O_RDWR, 0600);
  if (descriptor < 0) {
    return false;
  }
  const ssize_t written =
      write(descriptor, kWasmFsPayload.data(), kWasmFsPayload.size());
  if (written != static_cast<ssize_t>(kWasmFsPayload.size()) ||
      fsync(descriptor) != 0 || lseek(descriptor, 0, SEEK_SET) != 0) {
    close(descriptor);
    return false;
  }
  std::array<char, 64> buffer{};
  const ssize_t read_count = read(descriptor, buffer.data(), buffer.size());
  const bool matches =
      read_count == static_cast<ssize_t>(kWasmFsPayload.size()) &&
      std::memcmp(buffer.data(), kWasmFsPayload.data(), kWasmFsPayload.size()) ==
          0;
  return close(descriptor) == 0 && matches;
}

void audio_processor_created(EMSCRIPTEN_WEBAUDIO_T context,
                             bool success,
                             void* user_data) {
  if (!success) {
    audio_state.store(-3, std::memory_order_release);
    return;
  }
  int output_channel_counts[1] = {2};
  EmscriptenAudioWorkletNodeCreateOptions options = {
      .numberOfInputs = 0,
      .numberOfOutputs = 1,
      .outputChannelCounts = output_channel_counts,
      .channelCount = 2,
      .channelCountMode = WEBAUDIO_CHANNEL_COUNT_MODE_EXPLICIT,
      .channelInterpretation = WEBAUDIO_CHANNEL_INTERPRETATION_DISCRETE,
  };
  audio_node = emscripten_create_wasm_audio_worklet_node(
      context, "lmdj-toolchain-probe", &options, process_probe, nullptr);
  if (audio_node == 0) {
    audio_state.store(-4, std::memory_order_release);
    return;
  }
  configured_channels.store(2, std::memory_order_release);
  EM_ASM({
    const context = emscriptenGetAudioObject($0);
    const node = emscriptenGetAudioObject($1);
    const splitter = context.createChannelSplitter(2);
    const analyser = context.createAnalyser();
    analyser.fftSize = 256;
    node.connect(splitter);
    splitter.connect(analyser, 1, 0);
    analyser.connect(context.destination);
    Module["lmdjAudioContext"] = context;
    Module["lmdjAudioNode"] = node;
    Module["lmdjChannelSplitter"] = splitter;
    Module["lmdjAnalyser"] = analyser;
  }, context, audio_node);
  audio_ready.store(1, std::memory_order_release);
}

void audio_worklet_initialized(EMSCRIPTEN_WEBAUDIO_T context,
                               bool success,
                               void* user_data) {
  if (!success) {
    audio_state.store(-2, std::memory_order_release);
    return;
  }
  const WebAudioWorkletProcessorCreateOptions options = {
      .name = "lmdj-toolchain-probe",
      .numAudioParams = 0,
      .audioParamDescriptors = nullptr,
  };
  emscripten_create_wasm_audio_worklet_processor_async(
      context, &options, audio_processor_created, nullptr);
}

}  // namespace

extern "C" EMSCRIPTEN_KEEPALIVE int lmdj_start_audio_probe() {
  if (!emscripten_is_main_browser_thread()) {
    return -1;
  }
  if (audio_context != 0) {
    emscripten_resume_audio_context_sync(audio_context);
    return 1;
  }
  const EmscriptenWebAudioCreateAttributes attributes = {
      .latencyHint = "interactive",
      .sampleRate = 48'000,
      .renderSizeHint = AUDIO_CONTEXT_RENDER_SIZE_DEFAULT,
  };
  audio_context = emscripten_create_audio_context(&attributes);
  if (audio_context == 0) {
    return -2;
  }
  const int observed_sample_rate =
      emscripten_audio_context_sample_rate(audio_context);
  if (observed_sample_rate != 48'000) {
    audio_state.store(-5, std::memory_order_release);
    return -3;
  }
  audio_state.store(1, std::memory_order_release);
  emscripten_start_wasm_audio_worklet_thread_async(
      audio_context,
      audio_worklet_stack.data(),
      audio_worklet_stack.size(),
      audio_worklet_initialized,
      nullptr);
  emscripten_resume_audio_context_sync(audio_context);
  return 1;
}

extern "C" EMSCRIPTEN_KEEPALIVE int lmdj_get_audio_context() {
  return audio_context;
}

extern "C" EMSCRIPTEN_KEEPALIVE int lmdj_get_audio_state() {
  return audio_state.load(std::memory_order_acquire);
}

extern "C" EMSCRIPTEN_KEEPALIVE int lmdj_get_audio_ready() {
  return audio_ready.load(std::memory_order_acquire);
}

extern "C" EMSCRIPTEN_KEEPALIVE int lmdj_get_configured_channels() {
  return configured_channels.load(std::memory_order_acquire);
}

extern "C" EMSCRIPTEN_KEEPALIVE int lmdj_get_control_browser_main() {
  return control_browser_main.load(std::memory_order_acquire);
}

extern "C" EMSCRIPTEN_KEEPALIVE int lmdj_get_control_done() {
  return control_done.load(std::memory_order_acquire);
}

extern "C" EMSCRIPTEN_KEEPALIVE int lmdj_get_control_probes() {
  return control_probes.load(std::memory_order_acquire);
}

extern "C" EMSCRIPTEN_KEEPALIVE int lmdj_get_observed_frames() {
  return observed_callback_frames(
      shared_probe_word.load(std::memory_order_acquire));
}

extern "C" EMSCRIPTEN_KEEPALIVE int lmdj_get_shared_marker() {
  return (shared_probe_word.load(std::memory_order_acquire) &
          kSharedMarkerMask) != 0U
             ? 1
             : 0;
}

extern "C" EMSCRIPTEN_KEEPALIVE int lmdj_get_quantum_mismatch() {
  return (shared_probe_word.load(std::memory_order_acquire) &
          kQuantumMismatchMask) != 0U
             ? 1
             : 0;
}

extern "C" EMSCRIPTEN_KEEPALIVE int lmdj_get_observed_sample_rate() {
  return audio_context == 0
             ? 0
             : emscripten_audio_context_sample_rate(audio_context);
}

extern "C" EMSCRIPTEN_KEEPALIVE void lmdj_observe_quantum_for_test(int frames) {
  record_callback_frames(shared_probe_word, frames);
}

extern "C" EMSCRIPTEN_KEEPALIVE int lmdj_get_wasmfs_ok() {
  return wasmfs_ok.load(std::memory_order_acquire);
}

extern "C" EMSCRIPTEN_KEEPALIVE const char* lmdj_get_lease_json() {
  return lease_json.data();
}

extern "C" EMSCRIPTEN_KEEPALIVE const char* lmdj_get_iteration_json() {
  return iteration_json.data();
}

extern "C" EMSCRIPTEN_KEEPALIVE const char* lmdj_get_replacement_json() {
  return replacement_json.data();
}

int main() {
  control_browser_main.store(
      emscripten_is_main_browser_thread() ? 1 : 0,
      std::memory_order_release);
  wasmfs_ok.store(run_wasmfs_probe() ? 1 : -1, std::memory_order_release);

  const int lease_ok =
      lmdj_opfs_acquire_writer(lease_json.data(), lease_json.size());
  const int iteration_ok =
      lmdj_opfs_list_names(iteration_json.data(), iteration_json.size());
  const int replacement_ok = lmdj_opfs_replace_complete(
      replacement_json.data(), replacement_json.size());
  if (lease_ok != 1 || iteration_ok != 1 || replacement_ok != 1) {
    control_done.store(-1, std::memory_order_release);
  }

  shared_probe_word.fetch_or(kSharedMarkerMask, std::memory_order_release);
  const double deadline = emscripten_performance_now() + 30'000.0;
  while (observed_callback_frames(
             shared_probe_word.load(std::memory_order_acquire)) == 0 &&
         emscripten_performance_now() < deadline) {
    emscripten_thread_sleep(1);
  }
  if (observed_callback_frames(
          shared_probe_word.load(std::memory_order_acquire)) == 0) {
    control_done.store(-2, std::memory_order_release);
    return 2;
  }

  for (int index = 0; index < kControlProbeCount; ++index) {
    MAIN_THREAD_EM_ASM({
      Module["lmdjMainThreadProbeCount"] += 1;
    });
    control_probes.store(index + 1, std::memory_order_release);
    emscripten_thread_sleep(1);
  }
  if (control_done.load(std::memory_order_acquire) == 0) {
    control_done.store(1, std::memory_order_release);
  }
  emscripten_exit_with_live_runtime();
  return 0;
}

#else
#error "define one Task 0 probe compilation role"
#endif
