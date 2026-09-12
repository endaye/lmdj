# CMake generated Testfile for 
# Source directory: /home/en/lmdj/packages/project-cooker
# Build directory: /home/en/lmdj/build/dev/packages/project-cooker
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test([=[cooker.runtime_content]=] "/home/en/lmdj/build/dev/bin/lmdj_runtime_content_tests")
set_tests_properties([=[cooker.runtime_content]=] PROPERTIES  LABELS "unit;;native" TIMEOUT "10" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/project-cooker/CMakeLists.txt;44;lmdj_add_test;/home/en/lmdj/packages/project-cooker/CMakeLists.txt;0;")
add_test([=[cooker.sample_analysis]=] "/home/en/lmdj/build/dev/bin/lmdj_project_cooker_sample_analysis_tests")
set_tests_properties([=[cooker.sample_analysis]=] PROPERTIES  LABELS "unit;audio;native" TIMEOUT "10" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/project-cooker/CMakeLists.txt;66;lmdj_add_test;/home/en/lmdj/packages/project-cooker/CMakeLists.txt;0;")
add_test([=[cooker.project]=] "/home/en/lmdj/build/dev/bin/lmdj_project_cooker_tests")
set_tests_properties([=[cooker.project]=] PROPERTIES  LABELS "component;audio;native" TIMEOUT "30" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/project-cooker/CMakeLists.txt;90;lmdj_add_test;/home/en/lmdj/packages/project-cooker/CMakeLists.txt;0;")
add_test([=[cooker.determinism_matrix]=] "/home/en/lmdj/build/dev/bin/lmdj_project_cooker_determinism_matrix_tests")
set_tests_properties([=[cooker.determinism_matrix]=] PROPERTIES  LABELS "unit;audio;generated;native" TIMEOUT "10" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/project-cooker/CMakeLists.txt;114;lmdj_add_test;/home/en/lmdj/packages/project-cooker/CMakeLists.txt;0;")
add_test([=[cooker.performance_replay]=] "/home/en/lmdj/build/dev/bin/lmdj_project_cooker_performance_replay_tests")
set_tests_properties([=[cooker.performance_replay]=] PROPERTIES  LABELS "component;audio;native" TIMEOUT "30" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/project-cooker/CMakeLists.txt;138;lmdj_add_test;/home/en/lmdj/packages/project-cooker/CMakeLists.txt;0;")
add_test([=[cooker.wav_selection]=] "/home/en/lmdj/build/dev/bin/lmdj_project_cooker_wav_selection_tests")
set_tests_properties([=[cooker.wav_selection]=] PROPERTIES  LABELS "unit;audio;native" TIMEOUT "10" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/project-cooker/CMakeLists.txt;162;lmdj_add_test;/home/en/lmdj/packages/project-cooker/CMakeLists.txt;0;")
