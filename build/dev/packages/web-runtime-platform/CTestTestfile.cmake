# CMake generated Testfile for 
# Source directory: /home/en/lmdj/packages/web-runtime-platform
# Build directory: /home/en/lmdj/build/dev/packages/web-runtime-platform
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test([=[host.web_control_runtime]=] "/home/en/lmdj/build/dev/bin/lmdj_web_control_runtime_tests")
set_tests_properties([=[host.web_control_runtime]=] PROPERTIES  LABELS "host;audio;concurrency;native" TIMEOUT "120" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/web-runtime-platform/CMakeLists.txt;377;lmdj_add_test;/home/en/lmdj/packages/web-runtime-platform/CMakeLists.txt;0;")
add_test([=[host.web_manifest_gate]=] "/home/en/lmdj/build/dev/bin/lmdj_web_manifest_gate_tests")
set_tests_properties([=[host.web_manifest_gate]=] PROPERTIES  LABELS "host;;native" TIMEOUT "120" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/web-runtime-platform/CMakeLists.txt;408;lmdj_add_test;/home/en/lmdj/packages/web-runtime-platform/CMakeLists.txt;0;")
add_test([=[host.web_realtime_session]=] "/home/en/lmdj/build/dev/bin/lmdj_web_realtime_session_tests")
set_tests_properties([=[host.web_realtime_session]=] PROPERTIES  LABELS "host;audio;concurrency;native" TIMEOUT "120" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/web-runtime-platform/CMakeLists.txt;435;lmdj_add_test;/home/en/lmdj/packages/web-runtime-platform/CMakeLists.txt;0;")
add_test([=[host.web_performance_bridge]=] "/home/en/lmdj/build/dev/bin/lmdj_web_performance_bridge_tests")
set_tests_properties([=[host.web_performance_bridge]=] PROPERTIES  LABELS "host;audio;concurrency;native" TIMEOUT "120" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/web-runtime-platform/CMakeLists.txt;463;lmdj_add_test;/home/en/lmdj/packages/web-runtime-platform/CMakeLists.txt;0;")
add_test([=[host.web_source_boundary]=] "/home/en/.local/bin/python3.11" "/home/en/lmdj/apps/web-runtime-host/test/web_host_source_boundary_test.py" "/home/en/lmdj/apps/web-runtime-host")
set_tests_properties([=[host.web_source_boundary]=] PROPERTIES  LABELS "contract;" TIMEOUT "30" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/web-runtime-platform/CMakeLists.txt;470;lmdj_add_test;/home/en/lmdj/packages/web-runtime-platform/CMakeLists.txt;0;")
add_test([=[platform.web_runtime_source_boundary]=] "/home/en/.local/bin/python3.11" "/home/en/lmdj/packages/web-runtime-platform/test/source_boundary_test.py")
set_tests_properties([=[platform.web_runtime_source_boundary]=] PROPERTIES  LABELS "contract;" TIMEOUT "30" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/web-runtime-platform/CMakeLists.txt;479;lmdj_add_test;/home/en/lmdj/packages/web-runtime-platform/CMakeLists.txt;0;")
add_test([=[host.soundset_refusal_ownership]=] "/home/en/.local/bin/python3.11" "/home/en/lmdj/tests/host/soundset_refusal_ownership_test.py")
set_tests_properties([=[host.soundset_refusal_ownership]=] PROPERTIES  LABELS "contract;" TIMEOUT "30" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/web-runtime-platform/CMakeLists.txt;491;lmdj_add_test;/home/en/lmdj/packages/web-runtime-platform/CMakeLists.txt;0;")
