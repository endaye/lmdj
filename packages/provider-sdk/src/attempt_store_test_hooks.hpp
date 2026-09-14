#pragma once

// Only the dedicated crash-test executable compiles the instrumented translation
// unit. No hook, environment variable or fault dispatcher enters the SDK archive.
#ifdef LMDJ_PROVIDER_TEST_CHECKPOINTS
#include <string_view>
namespace lmdj::provider::test {
void checkpoint(std::string_view name);
}
#define LMDJ_PROVIDER_CHECKPOINT(name) ::lmdj::provider::test::checkpoint(name)
#else
#define LMDJ_PROVIDER_CHECKPOINT(name) ((void)0)
#endif
