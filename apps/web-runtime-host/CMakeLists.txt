file(READ "${CMAKE_SOURCE_DIR}/products/lmdj/version.json" lmdj_web_version_json)
foreach(lmdj_web_version_part IN ITEMS milestone minor build patch)
  string(
    JSON lmdj_web_version_${lmdj_web_version_part}
    GET "${lmdj_web_version_json}" "${lmdj_web_version_part}"
  )
endforeach()

set(
  LMDJ_WEB_SELECTED_PRODUCT_BUILD
  "${lmdj_web_version_milestone}.${lmdj_web_version_minor}.${lmdj_web_version_build}.${lmdj_web_version_patch}"
  PARENT_SCOPE
)
set(
  LMDJ_WEB_SELECTED_DISTRIBUTION_CONTRACT
  "lmdj.web-runtime-host.distribution.v1"
  PARENT_SCOPE
)
set(LMDJ_WEB_SELECTED_HOST_ID "web-runtime-host" PARENT_SCOPE)
set(LMDJ_WEB_SELECTED_HOST_VERSION "1.1.0" PARENT_SCOPE)
set(LMDJ_WEB_SELECTED_PLATFORM_VERSION "0.1.0" PARENT_SCOPE)
