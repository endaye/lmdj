include(FetchContent)

FetchContent_Declare(
  nlohmann_json
  URL https://github.com/nlohmann/json/releases/download/v3.12.0/json.tar.xz
  URL_HASH SHA256=42f6e95cad6ec532fd372391373363b62a14af6d771056dbfc86160e6dfff7aa
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)

FetchContent_Declare(
  picosha2
  GIT_REPOSITORY https://github.com/okdshin/PicoSHA2.git
  GIT_TAG 161cb3fc4170fa7a3eca9e582cebd27cc4d1fe29
  GIT_SHALLOW FALSE
)

FetchContent_MakeAvailable(nlohmann_json picosha2)

add_library(lmdj_picosha2 ALIAS picosha2)
