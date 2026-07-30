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
  if(NOT LMDJ_ENABLE_SANITIZERS)
    return()
  endif()

  if(MSVC)
    message(FATAL_ERROR "LMDJ_ENABLE_SANITIZERS is unsupported with MSVC")
  endif()

  target_compile_options(
    "${target}"
    PRIVATE
      -fsanitize=address,undefined
      -fno-omit-frame-pointer
  )
  target_link_options(
    "${target}"
    PRIVATE
      -fsanitize=address,undefined
  )
endfunction()
