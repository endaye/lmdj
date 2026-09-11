idf_component_register(SRCS main.cpp audio_driver.cpp runtime_host.cpp keyboard.cpp
  display.cpp input_controller.cpp transfer.cpp transfer_transaction.cpp transfer_session.cpp
  REQUIRES esp_driver_i2s esp_driver_i2c esp_driver_gpio freertos esp_system pthread)
target_include_directories(${COMPONENT_LIB} PRIVATE
  "${LMDJ_SOURCE_ROOT}/third_party/picosha2")
if(CMAKE_BUILD_EARLY_EXPANSION)
  return()
endif()

function(cardputer_core target module)
  set(sources)
  foreach(source IN LISTS ARGN)
    list(APPEND sources "${LMDJ_SOURCE_ROOT}/packages/${module}/src/${source}.cpp")
  endforeach()
  add_library(${target} STATIC ${sources})
  target_include_directories(${target} PUBLIC "${LMDJ_SOURCE_ROOT}/packages/${module}/include")
  target_include_directories(${target} PRIVATE "${LMDJ_SOURCE_ROOT}/third_party/picosha2")
  target_link_libraries(${target} PRIVATE idf::freertos idf::esp_system idf::pthread)
  target_compile_options(${target} PRIVATE -std=gnu++20 -fexceptions -Wall -Wextra -Wpedantic -Werror -fstack-usage)
endfunction()

cardputer_core(cardputer_foundation foundation artifact json soundset_manifest)
target_include_directories(cardputer_foundation SYSTEM PUBLIC "${LMDJ_JSON_INCLUDE}")
cardputer_core(cardputer_domain authoring-domain project migration command_handler)
target_link_libraries(cardputer_domain PUBLIC cardputer_foundation)
cardputer_core(cardputer_cooker project-cooker wav_reader wav_selection sample_analysis
  project_cooker performance_replay runtime_content)
target_link_libraries(cardputer_cooker PUBLIC cardputer_domain)
cardputer_core(cardputer_audio audio-runtime offline_renderer wav_writer master_fx
  prepared_sample_bank realtime_engine)
target_link_libraries(cardputer_audio PUBLIC cardputer_foundation cardputer_cooker)
cardputer_core(cardputer_facade application-facade runtime_facade)
target_link_libraries(cardputer_facade PUBLIC cardputer_cooker PRIVATE cardputer_audio)
target_link_libraries(${COMPONENT_LIB} PRIVATE cardputer_facade)
target_compile_options(${COMPONENT_LIB} PRIVATE -std=gnu++20 -fexceptions -Wall -Wextra -Wpedantic -Werror -fstack-usage)
target_compile_definitions(${COMPONENT_LIB} PRIVATE
  LMDJ_CARDPUTER_CONFIG_HEADER="${LMDJ_CARDPUTER_CONFIG_HEADER}"
  LMDJ_CARDPUTER_REVISION="${LMDJ_CARDPUTER_REVISION}")
