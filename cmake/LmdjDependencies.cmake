include(FetchContent)

# Both dependencies are vendored under third_party/ so that configure never
# reaches the network. Identities are unchanged from the previous download
# pins; see third_party/README.md for provenance and the update procedure.
set(LMDJ_THIRD_PARTY_DIR "${CMAKE_CURRENT_LIST_DIR}/../third_party")

FetchContent_Declare(
  nlohmann_json
  URL "${LMDJ_THIRD_PARTY_DIR}/nlohmann-json/json-v3.12.0.tar.xz"
  URL_HASH SHA256=42f6e95cad6ec532fd372391373363b62a14af6d771056dbfc86160e6dfff7aa
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)

FetchContent_Declare(
  picosha2
  SOURCE_DIR "${LMDJ_THIRD_PARTY_DIR}/picosha2"
)

FetchContent_MakeAvailable(nlohmann_json picosha2)

add_library(lmdj_picosha2 ALIAS picosha2)
