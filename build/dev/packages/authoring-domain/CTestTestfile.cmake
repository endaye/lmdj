# CMake generated Testfile for 
# Source directory: /home/en/lmdj/packages/authoring-domain
# Build directory: /home/en/lmdj/build/dev/packages/authoring-domain
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test([=[domain.project]=] "/home/en/lmdj/build/dev/bin/lmdj_domain_project_tests")
set_tests_properties([=[domain.project]=] PROPERTIES  LABELS "unit;;native" TIMEOUT "10" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/authoring-domain/CMakeLists.txt;40;lmdj_add_test;/home/en/lmdj/packages/authoring-domain/CMakeLists.txt;0;")
add_test([=[domain.command_handler]=] "/home/en/lmdj/build/dev/bin/lmdj_domain_command_handler_tests")
set_tests_properties([=[domain.command_handler]=] PROPERTIES  LABELS "unit;;native" TIMEOUT "10" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/authoring-domain/CMakeLists.txt;62;lmdj_add_test;/home/en/lmdj/packages/authoring-domain/CMakeLists.txt;0;")
add_test([=[domain.performance]=] "/home/en/lmdj/build/dev/bin/lmdj_domain_performance_tests")
set_tests_properties([=[domain.performance]=] PROPERTIES  LABELS "unit;;native" TIMEOUT "10" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/authoring-domain/CMakeLists.txt;84;lmdj_add_test;/home/en/lmdj/packages/authoring-domain/CMakeLists.txt;0;")
add_test([=[domain.migration_v4]=] "/home/en/lmdj/build/dev/bin/lmdj_domain_migration_v4_tests")
set_tests_properties([=[domain.migration_v4]=] PROPERTIES  LABELS "unit;;native" TIMEOUT "10" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/authoring-domain/CMakeLists.txt;111;lmdj_add_test;/home/en/lmdj/packages/authoring-domain/CMakeLists.txt;0;")
add_test([=[domain.soundset_map]=] "/home/en/lmdj/build/dev/bin/lmdj_domain_soundset_map_tests")
set_tests_properties([=[domain.soundset_map]=] PROPERTIES  LABELS "unit;;native" TIMEOUT "10" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/authoring-domain/CMakeLists.txt;133;lmdj_add_test;/home/en/lmdj/packages/authoring-domain/CMakeLists.txt;0;")
add_test([=[domain.soundset_install]=] "/home/en/lmdj/build/dev/bin/lmdj_domain_soundset_install_tests")
set_tests_properties([=[domain.soundset_install]=] PROPERTIES  LABELS "unit;;native" TIMEOUT "10" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/authoring-domain/CMakeLists.txt;155;lmdj_add_test;/home/en/lmdj/packages/authoring-domain/CMakeLists.txt;0;")
add_test([=[domain.candidate_adoption]=] "/home/en/lmdj/build/dev/bin/lmdj_domain_candidate_adoption_tests")
set_tests_properties([=[domain.candidate_adoption]=] PROPERTIES  LABELS "unit;;native" TIMEOUT "10" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/authoring-domain/CMakeLists.txt;176;lmdj_add_test;/home/en/lmdj/packages/authoring-domain/CMakeLists.txt;0;")
add_test([=[domain.model_sequence_seeds_0_63]=] "/home/en/lmdj/build/dev/bin/lmdj_domain_model_sequence_tests" "0" "63")
set_tests_properties([=[domain.model_sequence_seeds_0_63]=] PROPERTIES  LABELS "unit;domain;generated;native" TIMEOUT "10" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/authoring-domain/CMakeLists.txt;202;lmdj_add_test;/home/en/lmdj/packages/authoring-domain/CMakeLists.txt;0;")
add_test([=[domain.model_sequence_seeds_64_127]=] "/home/en/lmdj/build/dev/bin/lmdj_domain_model_sequence_tests" "64" "127")
set_tests_properties([=[domain.model_sequence_seeds_64_127]=] PROPERTIES  LABELS "unit;domain;generated;native" TIMEOUT "10" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/authoring-domain/CMakeLists.txt;209;lmdj_add_test;/home/en/lmdj/packages/authoring-domain/CMakeLists.txt;0;")
add_test([=[domain.model_sequence_seeds_128_191]=] "/home/en/lmdj/build/dev/bin/lmdj_domain_model_sequence_tests" "128" "191")
set_tests_properties([=[domain.model_sequence_seeds_128_191]=] PROPERTIES  LABELS "unit;domain;generated;native" TIMEOUT "10" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/authoring-domain/CMakeLists.txt;216;lmdj_add_test;/home/en/lmdj/packages/authoring-domain/CMakeLists.txt;0;")
add_test([=[domain.model_sequence_seeds_192_255]=] "/home/en/lmdj/build/dev/bin/lmdj_domain_model_sequence_tests" "192" "255")
set_tests_properties([=[domain.model_sequence_seeds_192_255]=] PROPERTIES  LABELS "unit;domain;generated;native" TIMEOUT "10" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/authoring-domain/CMakeLists.txt;223;lmdj_add_test;/home/en/lmdj/packages/authoring-domain/CMakeLists.txt;0;")
