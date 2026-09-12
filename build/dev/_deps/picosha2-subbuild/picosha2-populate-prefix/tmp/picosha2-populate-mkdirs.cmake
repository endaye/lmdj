# Distributed under the OSI-approved BSD 3-Clause License.  See accompanying
# file Copyright.txt or https://cmake.org/licensing for details.

cmake_minimum_required(VERSION 3.5)

file(MAKE_DIRECTORY
  "/home/en/lmdj/cmake/../third_party/picosha2"
  "/home/en/lmdj/build/dev/_deps/picosha2-build"
  "/home/en/lmdj/build/dev/_deps/picosha2-subbuild/picosha2-populate-prefix"
  "/home/en/lmdj/build/dev/_deps/picosha2-subbuild/picosha2-populate-prefix/tmp"
  "/home/en/lmdj/build/dev/_deps/picosha2-subbuild/picosha2-populate-prefix/src/picosha2-populate-stamp"
  "/home/en/lmdj/build/dev/_deps/picosha2-subbuild/picosha2-populate-prefix/src"
  "/home/en/lmdj/build/dev/_deps/picosha2-subbuild/picosha2-populate-prefix/src/picosha2-populate-stamp"
)

set(configSubDirs )
foreach(subDir IN LISTS configSubDirs)
    file(MAKE_DIRECTORY "/home/en/lmdj/build/dev/_deps/picosha2-subbuild/picosha2-populate-prefix/src/picosha2-populate-stamp/${subDir}")
endforeach()
if(cfgdir)
  file(MAKE_DIRECTORY "/home/en/lmdj/build/dev/_deps/picosha2-subbuild/picosha2-populate-prefix/src/picosha2-populate-stamp${cfgdir}") # cfgdir has leading slash
endif()
