# CMake generated Testfile for 
# Source directory: /home/en/lmdj/packages/foundation
# Build directory: /home/en/lmdj/build/dev/packages/foundation
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test([=[foundation.artifact]=] "/home/en/lmdj/build/dev/bin/lmdj_foundation_tests")
set_tests_properties([=[foundation.artifact]=] PROPERTIES  LABELS "unit;;native" TIMEOUT "10" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/foundation/CMakeLists.txt;43;lmdj_add_test;/home/en/lmdj/packages/foundation/CMakeLists.txt;0;")
add_test([=[foundation.json]=] "/home/en/lmdj/build/dev/bin/lmdj_foundation_json_tests")
set_tests_properties([=[foundation.json]=] PROPERTIES  LABELS "unit;;native" TIMEOUT "10" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/foundation/CMakeLists.txt;66;lmdj_add_test;/home/en/lmdj/packages/foundation/CMakeLists.txt;0;")
add_test([=[foundation.soundset_manifest]=] "/home/en/lmdj/build/dev/bin/lmdj_foundation_soundset_manifest_tests")
set_tests_properties([=[foundation.soundset_manifest]=] PROPERTIES  LABELS "unit;;native" TIMEOUT "10" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/foundation/CMakeLists.txt;94;lmdj_add_test;/home/en/lmdj/packages/foundation/CMakeLists.txt;0;")
