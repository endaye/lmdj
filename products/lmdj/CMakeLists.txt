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
    lmdj_provider_local_sample_slice
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
  target_link_options(lmdj_web_runtime_host PRIVATE
    "SHELL:--embed-file ${CMAKE_CURRENT_SOURCE_DIR}/assembly.json@/lmdj-product/assembly.json"
    "SHELL:--embed-file ${CMAKE_SOURCE_DIR}/contracts/assembly/lmdj.assembly.v2.schema.json@/lmdj-product/contracts/assembly/lmdj.assembly.v2.schema.json")
  set_property(TARGET lmdj_web_runtime_host APPEND PROPERTY LINK_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/assembly.json"
    "${CMAKE_SOURCE_DIR}/contracts/assembly/lmdj.assembly.v2.schema.json")
  file(READ "${CMAKE_CURRENT_SOURCE_DIR}/version.json" lmdj_web_version_json)
  file(
    READ
    "${CMAKE_CURRENT_SOURCE_DIR}/generated/web-runtime-identity.json"
    lmdj_web_identity_json
  )
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
  string(
    JSON lmdj_web_platform_version
    GET "${lmdj_web_identity_json}" platform version
  )
  string(
    JSON lmdj_web_creator_host_version
    GET "${lmdj_web_identity_json}" hosts creator-web version
  )
  string(
    JSON lmdj_web_diagnostic_host_version
    GET "${lmdj_web_identity_json}" hosts web-runtime-host version
  )
  target_compile_definitions(
    lmdj_web_runtime_host
    PRIVATE
      LMDJ_WEB_PRODUCT_BUILD="${lmdj_web_product_build}"
      LMDJ_WEB_PLATFORM_VERSION="${lmdj_web_platform_version}"
      LMDJ_WEB_CREATOR_DISTRIBUTION_CONTRACT="lmdj.creator-web.distribution.v1"
      LMDJ_WEB_CREATOR_HOST_ID="creator-web"
      LMDJ_WEB_CREATOR_HOST_VERSION="${lmdj_web_creator_host_version}"
      LMDJ_WEB_DIAGNOSTIC_DISTRIBUTION_CONTRACT="lmdj.web-runtime-host.distribution.v1"
      LMDJ_WEB_DIAGNOSTIC_HOST_ID="web-runtime-host"
      LMDJ_WEB_DIAGNOSTIC_HOST_VERSION="${lmdj_web_diagnostic_host_version}"
  )
  target_link_libraries(
    lmdj_web_runtime_host
    PRIVATE
      lmdj_product_lmdj_assembly
  )
endif()

if(TARGET lmdj_assembly_loader_tests)
  target_link_libraries(lmdj_assembly_loader_tests PRIVATE
    lmdj_product_lmdj_assembly lmdj_provider_local_sample_slice)
endif()

if(TARGET lmdj_facade_provider_owner_tests)
  target_link_libraries(lmdj_facade_provider_owner_tests PRIVATE
    lmdj_product_lmdj_assembly lmdj_provider_local_sample_slice)
endif()

if(TARGET lmdj_web_control_runtime_tests)
  target_link_libraries(lmdj_web_control_runtime_tests PRIVATE lmdj_product_lmdj_assembly)
  target_compile_definitions(lmdj_web_control_runtime_tests PRIVATE
    LMDJ_TEST_ASSEMBLY_PATH="${CMAKE_CURRENT_SOURCE_DIR}/assembly.json")
endif()

if(TARGET lmdj_facade_candidate_job_tests)
  target_include_directories(lmdj_facade_candidate_job_tests PRIVATE
    "${CMAKE_SOURCE_DIR}/packages/application-facade/internal")
  target_link_libraries(lmdj_facade_candidate_job_tests PRIVATE
    lmdj_product_lmdj_assembly)
endif()

if(TARGET lmdj_facade_candidate_store_tests)
  target_include_directories(lmdj_facade_candidate_store_tests PRIVATE
    "${CMAKE_SOURCE_DIR}/packages/application-facade/internal")
  target_link_libraries(lmdj_facade_candidate_store_tests PRIVATE lmdj_product_lmdj_assembly)
endif()

if(TARGET lmdj_facade_candidate_adoption_tests)
  target_link_libraries(lmdj_facade_candidate_adoption_tests PRIVATE lmdj_product_lmdj_assembly)
endif()

if(TARGET lmdj_facade_candidate_audition_tests)
  target_link_libraries(lmdj_facade_candidate_audition_tests PRIVATE lmdj_product_lmdj_assembly)
endif()
