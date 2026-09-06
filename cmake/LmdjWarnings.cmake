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
    # GCC's shared libtsan/libasan already do. The runtime lives in the
    # compiler's resource directory, which is not on the loader's search path,
    # and -frtlib-add-rpath records nothing under Debian's lib/linux layout
    # (verified on clang-22: no RUNPATH, `cannot open shared object file`), so
    # the rpath is written explicitly from the compiler's own answer. Apple
    # Clang links its sanitizer runtimes shared unconditionally.
    if(NOT DEFINED LMDJ_CLANG_RUNTIME_DIR)
      execute_process(
        COMMAND "${CMAKE_CXX_COMPILER}" -print-runtime-dir
        RESULT_VARIABLE lmdj_runtime_dir_status
        OUTPUT_VARIABLE lmdj_runtime_dir
        OUTPUT_STRIP_TRAILING_WHITESPACE
      )
      if(NOT lmdj_runtime_dir_status EQUAL 0 OR NOT IS_DIRECTORY "${lmdj_runtime_dir}")
        message(FATAL_ERROR
          "why: ${CMAKE_CXX_COMPILER} -print-runtime-dir did not name a "
          "directory, so the shared sanitizer runtime cannot be located for "
          "rpath; remedy: install the matching libclang-rt-<major>-dev package "
          "(scripts/ci/host/install-llvm-toolchain.sh) or select a compiler "
          "whose runtime directory exists")
      endif()
      set(LMDJ_CLANG_RUNTIME_DIR "${lmdj_runtime_dir}" CACHE INTERNAL
        "Clang compiler-rt runtime directory used for the shared sanitizer rpath")
    endif()
    # -Wl, rather than CMake's LINKER: abstraction: this branch is already
    # narrowed to Clang on Linux, whose driver always takes -Wl, so the
    # abstraction buys no portability here, and writing it directly keeps the
    # flag independent of which CMake version interprets the prefix.
    list(APPEND lmdj_sanitizer_link_flags
      -shared-libsan "-Wl,-rpath,${LMDJ_CLANG_RUNTIME_DIR}")
  endif()
  target_link_options(
    "${target}"
    PRIVATE
      "${lmdj_sanitizer_link_flags}"
  )
endfunction()
