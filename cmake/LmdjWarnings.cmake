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
  target_link_options(
    "${target}"
    PRIVATE
      "${lmdj_sanitizer_flags}"
  )
endfunction()
