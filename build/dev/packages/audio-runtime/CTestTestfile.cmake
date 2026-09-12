# CMake generated Testfile for 
# Source directory: /home/en/lmdj/packages/audio-runtime
# Build directory: /home/en/lmdj/build/dev/packages/audio-runtime
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test([=[audio.prepared_sample_bank]=] "/home/en/lmdj/build/dev/bin/lmdj_prepared_sample_bank_tests")
set_tests_properties([=[audio.prepared_sample_bank]=] PROPERTIES  LABELS "component;audio;native" TIMEOUT "30" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;81;lmdj_add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;0;")
add_test([=[audio.realtime_engine]=] "/home/en/lmdj/build/dev/bin/lmdj_realtime_engine_tests")
set_tests_properties([=[audio.realtime_engine]=] PROPERTIES  LABELS "component;audio;concurrency;native" TIMEOUT "30" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;106;lmdj_add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;0;")
add_test([=[audio.snapshot_publication_invariant]=] "/home/en/lmdj/build/dev/bin/lmdj_snapshot_publication_invariant_tests")
set_tests_properties([=[audio.snapshot_publication_invariant]=] PROPERTIES  LABELS "component;audio;concurrency;native" TIMEOUT "30" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;125;lmdj_add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;0;")
add_test([=[audio.realtime_queue]=] "/home/en/lmdj/build/dev/bin/lmdj_audio_realtime_queue_tests")
set_tests_properties([=[audio.realtime_queue]=] PROPERTIES  LABELS "unit;audio;concurrency;native" TIMEOUT "10" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;144;lmdj_add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;0;")
add_test([=[audio.value_channel]=] "/home/en/lmdj/build/dev/bin/lmdj_audio_value_channel_tests")
set_tests_properties([=[audio.value_channel]=] PROPERTIES  LABELS "unit;audio;concurrency;native" TIMEOUT "10" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;163;lmdj_add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;0;")
add_test([=[audio.master_fx]=] "/home/en/lmdj/build/dev/bin/lmdj_master_fx_tests")
set_tests_properties([=[audio.master_fx]=] PROPERTIES  LABELS "component;audio;native" TIMEOUT "30" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;182;lmdj_add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;0;")
add_test([=[audio.master_fx_determinism]=] "/home/en/lmdj/build/dev/bin/lmdj_master_fx_determinism_tests")
set_tests_properties([=[audio.master_fx_determinism]=] PROPERTIES  LABELS "component;audio;concurrency;native" TIMEOUT "30" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;201;lmdj_add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;0;")
add_test([=[audio.master_fx_allocation_guard]=] "/home/en/lmdj/build/dev/bin/lmdj_master_fx_allocation_guard_tests")
set_tests_properties([=[audio.master_fx_allocation_guard]=] PROPERTIES  LABELS "component;audio;concurrency;native" TIMEOUT "30" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;220;lmdj_add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;0;")
add_test([=[audio.realtime_spsc_stress]=] "/home/en/lmdj/build/dev/bin/lmdj_realtime_engine_stress_tests")
set_tests_properties([=[audio.realtime_spsc_stress]=] PROPERTIES  LABELS "stress;audio;concurrency;native" TIMEOUT "180" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;242;lmdj_add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;0;")
add_test([=[audio.snapshot_publication_stress]=] "/home/en/lmdj/build/dev/bin/lmdj_snapshot_publication_stress_tests")
set_tests_properties([=[audio.snapshot_publication_stress]=] PROPERTIES  LABELS "stress;audio;concurrency;native" TIMEOUT "180" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;263;lmdj_add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;0;")
add_test([=[audio.long_sample_publication_stress]=] "/home/en/lmdj/build/dev/bin/lmdj_long_sample_publication_stress_tests")
set_tests_properties([=[audio.long_sample_publication_stress]=] PROPERTIES  LABELS "stress;audio;concurrency;native" TIMEOUT "180" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;284;lmdj_add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;0;")
add_test([=[audio.master_fx_stress]=] "/home/en/lmdj/build/dev/bin/lmdj_master_fx_stress_tests")
set_tests_properties([=[audio.master_fx_stress]=] PROPERTIES  LABELS "stress;audio;concurrency;native" TIMEOUT "180" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;316;lmdj_add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;0;")
add_test([=[audio.offline_renderer]=] "/home/en/lmdj/build/dev/bin/lmdj_audio_runtime_tests")
set_tests_properties([=[audio.offline_renderer]=] PROPERTIES  LABELS "component;audio;native" TIMEOUT "30" WORKING_DIRECTORY "/home/en/lmdj" _BACKTRACE_TRIPLES "/home/en/lmdj/cmake/LmdjTesting.cmake;40;add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;341;lmdj_add_test;/home/en/lmdj/packages/audio-runtime/CMakeLists.txt;0;")
