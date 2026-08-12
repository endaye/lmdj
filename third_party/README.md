# Vendored build dependencies

These are the two third-party sources the Core build requires. They are
vendored so that configuring, building, and verifying the Core never depends on
`github.com` availability at run time. Both were already pinned by content
identity before vendoring; vendoring changes the supply channel, not the
identity.

`scripts/verify-core-dependencies.sh` verifies these bytes offline and fails
closed on any mismatch. `cmake/LmdjDependencies.cmake` consumes them directly.

## nlohmann/json

| Field | Value |
| --- | --- |
| Upstream | <https://github.com/nlohmann/json> |
| Release | `v3.12.0` |
| Upstream asset | <https://github.com/nlohmann/json/releases/download/v3.12.0/json.tar.xz> |
| Vendored path | `nlohmann-json/json-v3.12.0.tar.xz` |
| SHA-256 | `42f6e95cad6ec532fd372391373363b62a14af6d771056dbfc86160e6dfff7aa` |
| License | MIT, as `json/LICENSE.MIT` inside the archive |

The release archive is vendored unmodified, so the pinned SHA-256 is the same
value the previous `FetchContent` download verified.

## PicoSHA2

| Field | Value |
| --- | --- |
| Upstream | <https://github.com/okdshin/PicoSHA2> |
| Upstream commit | `161cb3fc4170fa7a3eca9e582cebd27cc4d1fe29` |
| Vendored path | `picosha2/` |
| License | MIT, as `picosha2/LICENSE` |

PicoSHA2 is a single-header library. Only the files the build needs are
vendored — `picosha2.h`, `CMakeLists.txt`, and `LICENSE`; the upstream `test/`
and `example/` trees are omitted and their CMake options stay `OFF`. Because a
vendored copy has no Git history, integrity is pinned by content hash instead
of by commit:

| File | SHA-256 |
| --- | --- |
| `picosha2/picosha2.h` | `b13c180161ffac8d0adc81e033e493c409457c4d1258ab9781ac80579ba3bdd8` |
| `picosha2/CMakeLists.txt` | `bf1de9a64c3f3bcc8bc338cc99158f74803af865e03fd13c960949c848a1bf19` |

The upstream commit above remains the provenance record: re-fetching that
commit and hashing the same three files reproduces these values.

## Updating a dependency

Vendored bytes are pinned inputs, not editable source. To move a version:
fetch the new upstream artifact, record its upstream URL/commit and new
hashes here, update the pins in `scripts/verify-core-dependencies.sh` and
`cmake/LmdjDependencies.cmake`, and run the Core Proof. Never edit vendored
files in place.
