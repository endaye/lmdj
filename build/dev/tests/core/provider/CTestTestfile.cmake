# CMake generated Testfile for 
# Source directory: /home/en/lmdj/tests/core/provider
# Build directory: /home/en/lmdj/build/dev/tests/core/provider
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test([=[provider.attempt_output_read]=] "/home/en/lmdj/build/dev/bin/lmdj_provider_attempt_output_read_tests")
set_tests_properties([=[provider.attempt_output_read]=] PROPERTIES  LABELS "component;provider;native" TIMEOUT "30" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;8;lmdj_add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;0;")
add_test([=[provider.sample_slice]=] "/home/en/lmdj/build/dev/bin/lmdj_provider_sample_slice_tests")
set_tests_properties([=[provider.sample_slice]=] PROPERTIES  LABELS "component;provider;native" TIMEOUT "30" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;18;lmdj_add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;0;")
add_test([=[provider.callback_stress]=] "/home/en/lmdj/build/dev/bin/lmdj_provider_callback_stress_tests")
set_tests_properties([=[provider.callback_stress]=] PROPERTIES  LABELS "stress;provider;native" TIMEOUT "300" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;25;lmdj_add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;0;")
add_test([=[provider.execution_crash]=] "/home/en/lmdj/build/dev/bin/lmdj_provider_execution_crash_tests")
set_tests_properties([=[provider.execution_crash]=] PROPERTIES  LABELS "component;provider;persistence;native" TIMEOUT "30" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;33;lmdj_add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;0;")
add_test([=[provider.output_validation]=] "/home/en/lmdj/build/dev/bin/lmdj_provider_output_validation_tests")
set_tests_properties([=[provider.output_validation]=] PROPERTIES  LABELS "component;provider;native" TIMEOUT "30" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;40;lmdj_add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;0;")
add_test([=[provider.artifact_source]=] "/home/en/lmdj/build/dev/bin/lmdj_provider_artifact_source_tests")
set_tests_properties([=[provider.artifact_source]=] PROPERTIES  LABELS "component;provider;native" TIMEOUT "30" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;46;lmdj_add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;0;")
add_test([=[provider.durable_file]=] "/home/en/lmdj/build/dev/bin/lmdj_provider_durable_file_tests")
set_tests_properties([=[provider.durable_file]=] PROPERTIES  LABELS "unit;provider;persistence;native" TIMEOUT "10" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;64;lmdj_add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;0;")
add_test([=[provider.conformance]=] "/home/en/lmdj/build/dev/bin/lmdj_provider_conformance_tests")
set_tests_properties([=[provider.conformance]=] PROPERTIES  LABELS "component;provider;native" TIMEOUT "30" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;89;lmdj_add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;0;")
add_test([=[provider.attempt_isolation]=] "/home/en/lmdj/build/dev/bin/lmdj_provider_attempt_isolation_tests")
set_tests_properties([=[provider.attempt_isolation]=] PROPERTIES  LABELS "component;provider;native" TIMEOUT "30" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;113;lmdj_add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;0;")
add_test([=[provider.attempt_ledger_invariant]=] "/home/en/lmdj/build/dev/bin/lmdj_provider_attempt_ledger_invariant_tests")
set_tests_properties([=[provider.attempt_ledger_invariant]=] PROPERTIES  LABELS "component;provider;persistence;native" TIMEOUT "30" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;138;lmdj_add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;0;")
add_test([=[provider.host_settings_invariant]=] "/home/en/lmdj/build/dev/bin/lmdj_provider_host_settings_invariant_tests")
set_tests_properties([=[provider.host_settings_invariant]=] PROPERTIES  LABELS "component;provider;persistence;native" TIMEOUT "30" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;163;lmdj_add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;0;")
add_test([=[provider.spec_regression]=] "/home/en/lmdj/build/dev/bin/lmdj_provider_spec_regression_tests")
set_tests_properties([=[provider.spec_regression]=] PROPERTIES  LABELS "component;provider;native" TIMEOUT "30" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;195;lmdj_add_test;/home/en/lmdj/tests/core/provider/CMakeLists.txt;0;")
