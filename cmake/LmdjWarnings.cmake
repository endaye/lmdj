set(
  LMDJ_SANITIZER
  "none"
  CACHE STRING
  "Core sanitizer mode: none, address, or thread"
)
set_property(
  CACHE LMDJ_SANITIZER
  PROPERTY STRINGS none address thread
)

if(
  NOT LMDJ_SANITIZER STREQUAL "none"
  AND NOT LMDJ_SANITIZER STREQUAL "address"
  AND NOT LMDJ_SANITIZER STREQUAL "thread"
)
  message(
    FATAL_ERROR
    "LMDJ_SANITIZER must be one of: none, address, thread"
  )
endif()

if(MSVC AND NOT LMDJ_SANITIZER STREQUAL "none")
  message(FATAL_ERROR "LMDJ_SANITIZER is unsupported with MSVC")
endif()

function(lmdj_target_warnings target)
  if(MSVC)
    target_compile_options("${target}" PRIVATE /W4 /WX)
  else()
    target_compile_options(
      "${target}"
      PRIVATE
        -Wall
        -Wextra
        -Wpedantic
        -Werror
    )
  endif()
endfunction()

function(lmdj_target_sanitizers target)
  if(LMDJ_SANITIZER STREQUAL "none")
    return()
  endif()

  if(LMDJ_SANITIZER STREQUAL "address")
    set(lmdj_sanitizer_flags -fsanitize=address,undefined)
  elseif(LMDJ_SANITIZER STREQUAL "thread")
    set(lmdj_sanitizer_flags -fsanitize=thread)
  endif()

  target_compile_options(
    "${target}"
    PRIVATE
      "${lmdj_sanitizer_flags}"
      -fno-omit-frame-pointer
  )
  set(lmdj_sanitizer_link_flags "${lmdj_sanitizer_flags}")
  if(CMAKE_CXX_COMPILER_ID STREQUAL "Clang" AND CMAKE_SYSTEM_NAME STREQUAL "Linux")
    # Clang on Linux links its sanitizer runtimes static and whole-archive by
    # default, and the C++ half (libclang_rt.tsan_cxx, libclang_rt.asan_cxx)
    # defines global operator new/delete. tests/core/audio/realtime_engine_test.cpp
    # replaces those operators to count allocations on the realtime path, so
    # the static link fails with `multiple definition` (#676 probe B). The
    # shared runtime resolves the operators by interposition the same way
    # GCC's shared libtsan/libasan already do, and -frtlib-add-rpath records
    # where the runtime lives so the tests run without LD_LIBRARY_PATH. Apple
    # Clang links its sanitizer runtimes shared unconditionally.
    list(APPEND lmdj_sanitizer_link_flags -shared-libsan -frtlib-add-rpath)
  endif()
  target_link_options(
    "${target}"
    PRIVATE
      "${lmdj_sanitizer_link_flags}"
  )
endfunction()
