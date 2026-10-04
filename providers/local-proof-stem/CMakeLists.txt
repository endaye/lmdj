set(lmdj_stem_package_files
  include/lmdj/providers/local_proof_stem/factory.hpp
  include/lmdj/providers/local_proof_stem/validation.hpp
  module.json
  src/provider.cpp
  src/validation.cpp
)
set(lmdj_stem_entries "")
foreach(relative IN LISTS lmdj_stem_package_files)
  set(absolute "${CMAKE_CURRENT_SOURCE_DIR}/${relative}")
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${absolute}")
  file(SHA256 "${absolute}" digest)
  list(APPEND lmdj_stem_entries "{\"path\":\"providers/local-proof-stem/${relative}\",\"sha256\":\"${digest}\"}")
endforeach()
list(JOIN lmdj_stem_entries "," lmdj_stem_files_json)
set(lmdj_stem_manifest "{\"files\":[${lmdj_stem_files_json}],\"format\":\"provider-source-package\",\"provider_id\":\"local.proof.stem\",\"provider_version\":\"1.0.0\"}\n")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/local.proof.stem.source-package.json" "${lmdj_stem_manifest}")
string(SHA256 lmdj_stem_package_sha256 "${lmdj_stem_manifest}")

add_library(lmdj_provider_local_proof_stem STATIC src/provider.cpp src/validation.cpp)
target_include_directories(lmdj_provider_local_proof_stem PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_link_libraries(lmdj_provider_local_proof_stem PUBLIC lmdj::provider_sdk lmdj_provider_local_sample_slice)
target_compile_definitions(lmdj_provider_local_proof_stem PRIVATE
  LMDJ_LOCAL_PROOF_STEM_SOURCE_PACKAGE_SHA256="${lmdj_stem_package_sha256}")
lmdj_target_warnings(lmdj_provider_local_proof_stem)
lmdj_target_sanitizers(lmdj_provider_local_proof_stem)
