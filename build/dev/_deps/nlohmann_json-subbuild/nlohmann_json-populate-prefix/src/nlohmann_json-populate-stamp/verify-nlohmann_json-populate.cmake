# Distributed under the OSI-approved BSD 3-Clause License.  See accompanying
# file Copyright.txt or https://cmake.org/licensing for details.

cmake_minimum_required(VERSION 3.5)

if("/home/en/lmdj/cmake/../third_party/nlohmann-json/json-v3.12.0.tar.xz" STREQUAL "")
  message(FATAL_ERROR "LOCAL can't be empty")
endif()

if(NOT EXISTS "/home/en/lmdj/cmake/../third_party/nlohmann-json/json-v3.12.0.tar.xz")
  message(FATAL_ERROR "File not found: /home/en/lmdj/cmake/../third_party/nlohmann-json/json-v3.12.0.tar.xz")
endif()

if("SHA256" STREQUAL "")
  message(WARNING "File will not be verified since no URL_HASH specified")
  return()
endif()

if("42f6e95cad6ec532fd372391373363b62a14af6d771056dbfc86160e6dfff7aa" STREQUAL "")
  message(FATAL_ERROR "EXPECT_VALUE can't be empty")
endif()

message(STATUS "verifying file...
     file='/home/en/lmdj/cmake/../third_party/nlohmann-json/json-v3.12.0.tar.xz'")

file("SHA256" "/home/en/lmdj/cmake/../third_party/nlohmann-json/json-v3.12.0.tar.xz" actual_value)

if(NOT "${actual_value}" STREQUAL "42f6e95cad6ec532fd372391373363b62a14af6d771056dbfc86160e6dfff7aa")
  message(FATAL_ERROR "error: SHA256 hash of
  /home/en/lmdj/cmake/../third_party/nlohmann-json/json-v3.12.0.tar.xz
does not match expected value
  expected: '42f6e95cad6ec532fd372391373363b62a14af6d771056dbfc86160e6dfff7aa'
    actual: '${actual_value}'
")
endif()

message(STATUS "verifying file... done")
