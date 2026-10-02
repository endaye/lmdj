# Initial cache for Emscripten configures only; never load this in a native
# configure, where find_package(Threads) must keep its real try-compile probe.
#
# why: under Emscripten the FindThreads probe answers are constant (-pthread
# works, and pthreads are not in plain libc), but every probe invokes emcc
# against the shared emsdk cache while sibling CI jobs link against it, and
# the concurrent cache-metadata access intermittently fails the probe and the
# whole wasm configure (#1783). Pre-seeding the constant results makes
# FindThreads skip both try-compiles: CMAKE_HAVE_LIBC_PTHREAD skips the libc
# probe, THREADS_HAVE_PTHREAD_ARG skips the "Check if compiler accepts
# -pthread" probe, and THREADS_PREFER_PTHREAD_FLAG records the -pthread
# compile and link flag on Threads::Threads, matching the successful probed
# outcome.
set(THREADS_PREFER_PTHREAD_FLAG ON CACHE BOOL "")
set(THREADS_HAVE_PTHREAD_ARG TRUE CACHE BOOL "")
set(CMAKE_HAVE_LIBC_PTHREAD FALSE CACHE INTERNAL "")
