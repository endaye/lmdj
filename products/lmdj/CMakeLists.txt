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
