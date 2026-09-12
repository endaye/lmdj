# CMake generated Testfile for 
# Source directory: /home/en/lmdj/apps/core-cli
# Build directory: /home/en/lmdj/build/dev/apps/core-cli
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test([=[host.cli]=] "/home/en/.local/bin/python3.11" "/home/en/lmdj/tests/host/cli_test.py" "/home/en/lmdj/build/dev/bin/lmdj-core")
set_tests_properties([=[host.cli]=] PROPERTIES  LABELS "host;" TIMEOUT "60" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/apps/core-cli/CMakeLists.txt;25;lmdj_add_test;/home/en/lmdj/apps/core-cli/CMakeLists.txt;0;")
add_test([=[host.performance-cli-session]=] "/home/en/.local/bin/python3.11" "/home/en/lmdj/tests/host/performance_cli_session_test.py" "/home/en/lmdj/build/dev/bin/lmdj-core")
set_tests_properties([=[host.performance-cli-session]=] PROPERTIES  LABELS "host;" TIMEOUT "90" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/apps/core-cli/CMakeLists.txt;35;lmdj_add_test;/home/en/lmdj/apps/core-cli/CMakeLists.txt;0;")
