#pragma once

#define LMDJ_CORE_C_API_VERSION 1

#define LMDJ_STATUS_OK 0
#define LMDJ_STATUS_INVALID_ARGUMENT 1
#define LMDJ_STATUS_INVALID_HANDLE 2
#define LMDJ_STATUS_ALLOCATION_FAILURE 3

#if defined(_WIN32)
#if defined(LMDJ_CORE_C_BUILD)
#define LMDJ_CORE_C_EXPORT __declspec(dllexport)
#else
#define LMDJ_CORE_C_EXPORT __declspec(dllimport)
#endif
#else
#define LMDJ_CORE_C_EXPORT __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef struct lmdj_engine lmdj_engine;

/*
 * config_json requires normalized absolute "workspace_root". Optional
 * normalized absolute "assembly_path" composes only the Providers declared by
 * that validated Product Assembly.
 */
LMDJ_CORE_C_EXPORT int lmdj_engine_create(
    const char* config_json,
    lmdj_engine** out_engine,
    char** out_error_json);

LMDJ_CORE_C_EXPORT int lmdj_engine_command(
    lmdj_engine* engine,
    const char* request_json,
    char** out_response_json);

LMDJ_CORE_C_EXPORT int lmdj_engine_query(
    lmdj_engine* engine,
    const char* request_json,
    char** out_response_json);

LMDJ_CORE_C_EXPORT void lmdj_string_free(char* value);
LMDJ_CORE_C_EXPORT void lmdj_engine_free(lmdj_engine* engine);

#ifdef __cplusplus
}
#endif
