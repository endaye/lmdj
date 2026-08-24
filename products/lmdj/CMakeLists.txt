add_library(
  lmdj_product_lmdj_assembly
  OBJECT
    src/compiled_assembly.cpp
)
target_link_libraries(
  lmdj_product_lmdj_assembly
  PRIVATE
    lmdj_provider_local_proof_success
    lmdj_provider_local_proof_failure
)
target_include_directories(
  lmdj_product_lmdj_assembly
  PRIVATE
    "${CMAKE_SOURCE_DIR}/packages/application-facade/include"
)
lmdj_target_warnings(lmdj_product_lmdj_assembly)
lmdj_target_sanitizers(lmdj_product_lmdj_assembly)

# Product-specific linking is owned here. The neutral Facade, C ABI, and Hosts
# only consume the installed compiled catalog.
target_link_libraries(
  lmdj_core_c
  PRIVATE
    lmdj_product_lmdj_assembly
)
target_link_libraries(
  lmdj_core_cli
  PRIVATE
    lmdj_product_lmdj_assembly
)
target_link_libraries(
  lmdj_native_host
  PRIVATE
    lmdj_product_lmdj_assembly
)
if(TARGET lmdj_web_runtime_host)
  file(READ "${CMAKE_CURRENT_SOURCE_DIR}/version.json" lmdj_web_version_json)
  foreach(lmdj_web_version_part IN ITEMS milestone minor build patch)
    string(
      JSON lmdj_web_version_${lmdj_web_version_part}
      GET "${lmdj_web_version_json}" "${lmdj_web_version_part}"
    )
  endforeach()
  set(
    lmdj_web_product_build
    "${lmdj_web_version_milestone}.${lmdj_web_version_minor}.${lmdj_web_version_build}.${lmdj_web_version_patch}"
  )
  target_compile_definitions(
    lmdj_web_runtime_host
    PRIVATE
      LMDJ_WEB_PRODUCT_BUILD="${lmdj_web_product_build}"
      LMDJ_WEB_PLATFORM_VERSION="0.3.6"
      LMDJ_WEB_CREATOR_DISTRIBUTION_CONTRACT="lmdj.creator-web.distribution.v1"
      LMDJ_WEB_CREATOR_HOST_ID="creator-web"
      LMDJ_WEB_CREATOR_HOST_VERSION="1.5.5"
      LMDJ_WEB_DIAGNOSTIC_DISTRIBUTION_CONTRACT="lmdj.web-runtime-host.distribution.v1"
      LMDJ_WEB_DIAGNOSTIC_HOST_ID="web-runtime-host"
      LMDJ_WEB_DIAGNOSTIC_HOST_VERSION="1.2.15"
  )
  target_link_libraries(
    lmdj_web_runtime_host
    PRIVATE
      lmdj_product_lmdj_assembly
  )
endif()
