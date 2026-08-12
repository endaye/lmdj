#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cstddef>
#include <exception>
#include <filesystem>
#include <fstream>
#include <future>
#include <iostream>
#include <iterator>
#include <optional>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

#include <picosha2.h>

#include <fcntl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>

#include <lmdj/foundation/error.hpp>
#include <lmdj/project_io/storage_platform.hpp>

#include "packages/project-io/src/testing_hooks.hpp"
#include "tests/core/support/test.hpp"

namespace {

using lmdj::foundation::ErrorCode;
using lmdj::project_io::make_default_project_storage_platform;
using lmdj::project_io::make_native_project_storage_platform;
using lmdj::project_io::testing::FaultPoint;

FaultPoint expected_fault = FaultPoint::transaction_temp_sync;
std::filesystem::path expected_final;
std::uintmax_t expected_size = 0;
int fault_calls = 0;
int active_journal_sync_calls = 0;
bool fault_phase_is_exact = false;
std::filesystem::path observed_sibling;
std::filesystem::path substitution_target;

bool lowercase_hex(std::string_view value) {
  return std::all_of(
      value.begin(),
      value.end(),
      [](unsigned char character) {
        return (character >= '0' && character <= '9') ||
               (character >= 'a' && character <= 'f');
      });
}

bool opaque_sibling_for(
    const std::filesystem::path& sibling,
    const std::filesystem::path& destination) {
  const auto sibling_name = sibling.filename().string();
  const auto prefix = destination.filename().string() + ".tmp.";
  std::error_code parent_error;
  const bool same_parent = std::filesystem::equivalent(
      sibling.parent_path(), destination.parent_path(), parent_error);
  return !parent_error && same_parent &&
         sibling_name.starts_with(prefix) &&
         sibling_name.size() == prefix.size() + 32 &&
         lowercase_hex(std::string_view{sibling_name}.substr(prefix.size()));
}

std::optional<std::filesystem::path> find_opaque_sibling(
    const std::filesystem::path& destination) {
  std::optional<std::filesystem::path> result;
  for (const auto& entry :
       std::filesystem::directory_iterator(destination.parent_path())) {
    if (!opaque_sibling_for(entry.path(), destination)) {
      continue;
    }
    LMDJ_CHECK(!result.has_value());
    result = entry.path();
  }
  return result;
}

lmdj::foundation::Result<void> observe_storage_fault(
    FaultPoint point,
    const std::filesystem::path& path) {
  if (point != expected_fault) {
    return lmdj::foundation::Result<void>::success();
  }
  ++fault_calls;
  std::error_code error;
  if (point == FaultPoint::transaction_temp_sync) {
    observed_sibling = path;
    fault_phase_is_exact =
        opaque_sibling_for(path, expected_final) &&
        std::filesystem::is_regular_file(path, error) && !error &&
        std::filesystem::file_size(path, error) == expected_size && !error &&
        !std::filesystem::exists(expected_final, error) && !error;
  } else if (point == FaultPoint::transaction_publish) {
    const auto sibling = find_opaque_sibling(expected_final);
    observed_sibling = sibling.value_or(std::filesystem::path{});
    fault_phase_is_exact =
        path == expected_final &&
        sibling.has_value() &&
        std::filesystem::is_regular_file(*sibling, error) && !error &&
        std::filesystem::file_size(*sibling, error) == expected_size && !error &&
        !std::filesystem::exists(expected_final, error) && !error;
  }
  return lmdj::foundation::Result<void>::failure(
      lmdj::foundation::Error{
          ErrorCode::io_error,
          "injected exact Native storage phase failure",
          {{"path", path.generic_string()}},
      });
}

lmdj::foundation::Result<void> substitute_storage_sibling(
    FaultPoint point,
    const std::filesystem::path& destination) {
  if (point != FaultPoint::transaction_publish &&
      point != FaultPoint::manifest_publish) {
    return lmdj::foundation::Result<void>::success();
  }
  const auto sibling = find_opaque_sibling(destination);
  LMDJ_CHECK(sibling.has_value());
  observed_sibling = *sibling;
  std::filesystem::remove(*sibling);
  std::filesystem::create_symlink(substitution_target, *sibling);
  return lmdj::foundation::Result<void>::success();
}

lmdj::foundation::Result<void> count_active_journal_sync(
    FaultPoint point,
    const std::filesystem::path&) {
  if (point == FaultPoint::active_journal_sync) {
    ++active_journal_sync_calls;
  }
  return lmdj::foundation::Result<void>::success();
}

class StorageFaultGuard {
 public:
  StorageFaultGuard() {
    fault_calls = 0;
    fault_phase_is_exact = false;
    observed_sibling.clear();
    lmdj::project_io::testing::set_fault_hook(observe_storage_fault);
  }

  ~StorageFaultGuard() {
    lmdj::project_io::testing::set_fault_hook(nullptr);
  }

  StorageFaultGuard(const StorageFaultGuard&) = delete;
  StorageFaultGuard& operator=(const StorageFaultGuard&) = delete;
};

class StorageHookGuard {
 public:
  explicit StorageHookGuard(lmdj::project_io::testing::FaultHook hook) {
    observed_sibling.clear();
    lmdj::project_io::testing::set_fault_hook(hook);
  }

  ~StorageHookGuard() {
    lmdj::project_io::testing::set_fault_hook(nullptr);
  }

  StorageHookGuard(const StorageHookGuard&) = delete;
  StorageHookGuard& operator=(const StorageHookGuard&) = delete;
};

class TempDirectory {
 public:
  TempDirectory() {
    const auto nonce =
        std::chrono::steady_clock::now().time_since_epoch().count();
    path_ = std::filesystem::temp_directory_path() /
            ("lmdj-storage-platform-test-" + std::to_string(nonce));
    std::filesystem::create_directories(path_);
  }

  ~TempDirectory() {
    std::error_code error;
    std::filesystem::remove_all(path_, error);
  }

  const std::filesystem::path& path() const { return path_; }

 private:
  std::filesystem::path path_;
};

std::vector<std::byte> bytes(std::string_view text) {
  std::vector<std::byte> result;
  result.reserve(text.size());
  for (const unsigned char character : text) {
    result.push_back(static_cast<std::byte>(character));
  }
  return result;
}

std::string text(const std::vector<std::byte>& input) {
  std::string result;
  result.reserve(input.size());
  for (const auto value : input) {
    result.push_back(static_cast<char>(std::to_integer<unsigned char>(value)));
  }
  return result;
}

void write_bytes(
    const std::filesystem::path& path,
    std::string_view input) {
  std::ofstream stream(path, std::ios::binary | std::ios::trunc);
  stream.write(input.data(), static_cast<std::streamsize>(input.size()));
  LMDJ_CHECK(static_cast<bool>(stream));
}

std::filesystem::path normalized_project_path(
    const std::filesystem::path& path) {
  auto normalized = std::filesystem::absolute(path).lexically_normal();
#if defined(__APPLE__)
  const auto relative = normalized.relative_path();
  if (!relative.empty()) {
    const auto first = *relative.begin();
    if (first == "var" || first == "tmp") {
      normalized = std::filesystem::path{"/private"} / relative;
    }
  }
#endif
  return normalized;
}

void test_writer_lease_is_reentrant_per_platform_and_competes_across_instances() {
  using namespace std::chrono_literals;
  TempDirectory temp;
  const auto bundle = temp.path() / "writer.lmdj";
  const auto metadata_root = temp.path() / "private-metadata/leases";
  auto first_platform = make_native_project_storage_platform(metadata_root);
  auto second_platform = make_native_project_storage_platform(metadata_root);
  LMDJ_CHECK(first_platform->ensure_directory(bundle).has_value());

  auto outer = first_platform->acquire_writer(bundle);
  LMDJ_CHECK(outer.has_value());
  LMDJ_CHECK(!std::filesystem::exists(bundle / ".lock"));
  const auto normalized = normalized_project_path(bundle).generic_string();
  const auto lease_path =
      metadata_root / (picosha2::hash256_hex_string(normalized) + ".lock");
  LMDJ_CHECK(std::filesystem::is_regular_file(lease_path));
  struct stat root_metadata {};
  struct stat lease_metadata {};
  LMDJ_CHECK(::stat(metadata_root.c_str(), &root_metadata) == 0);
  LMDJ_CHECK(::stat(lease_path.c_str(), &lease_metadata) == 0);
  LMDJ_CHECK((root_metadata.st_mode & 0777) == 0700);
  LMDJ_CHECK((lease_metadata.st_mode & 0777) == 0600);
  const auto original_lease_device = lease_metadata.st_dev;
  const auto original_lease_inode = lease_metadata.st_ino;

  auto nested = first_platform->acquire_writer(bundle / ".");
  LMDJ_CHECK(nested.has_value());

  const auto renamed_bundle = temp.path() / "renamed-writer.lmdj";
  std::filesystem::rename(bundle, renamed_bundle);
  std::filesystem::create_directory(bundle);

  auto competing = std::async(
      std::launch::async,
      [second_platform, bundle]() {
        return second_platform->acquire_writer(bundle);
      });
  LMDJ_CHECK(competing.wait_for(2s) == std::future_status::ready);
  auto rejected = competing.get();
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::io_error);
  LMDJ_CHECK(
      rejected.error().details.at("storage_condition") == "project_busy");

  std::filesystem::remove(bundle);
  std::filesystem::create_directory(bundle);
  auto recreated_busy = second_platform->acquire_writer(bundle);
  LMDJ_CHECK(!recreated_busy.has_value());
  LMDJ_CHECK(
      recreated_busy.error().details.at("storage_condition") ==
      "project_busy");
  LMDJ_CHECK(::stat(lease_path.c_str(), &lease_metadata) == 0);
  LMDJ_CHECK(lease_metadata.st_dev == original_lease_device);
  LMDJ_CHECK(lease_metadata.st_ino == original_lease_inode);

  nested.value().reset();
  auto still_busy = second_platform->acquire_writer(bundle);
  LMDJ_CHECK(!still_busy.has_value());
  LMDJ_CHECK(
      still_busy.error().details.at("storage_condition") == "project_busy");
  outer.value().reset();
  auto acquired = second_platform->acquire_writer(bundle);
  LMDJ_CHECK(acquired.has_value());
  LMDJ_CHECK(::stat(lease_path.c_str(), &lease_metadata) == 0);
  LMDJ_CHECK(lease_metadata.st_dev == original_lease_device);
  LMDJ_CHECK(lease_metadata.st_ino == original_lease_inode);
}

void test_writer_lease_rejects_hard_link_before_changing_permissions() {
  TempDirectory temp;
  const auto bundle = temp.path() / "hard-link-writer.lmdj";
  const auto metadata_root = temp.path() / "private-metadata/leases";
  std::filesystem::create_directories(bundle);
  std::filesystem::create_directories(metadata_root);
  LMDJ_CHECK(::chmod(metadata_root.c_str(), 0700) == 0);

  const auto normalized = normalized_project_path(bundle).generic_string();
  const auto lease_path =
      metadata_root / (picosha2::hash256_hex_string(normalized) + ".lock");
  const auto protected_file = temp.path() / "must-not-be-chmodded";
  write_bytes(protected_file, "protected");
  LMDJ_CHECK(::chmod(protected_file.c_str(), 0640) == 0);
  std::filesystem::create_hard_link(protected_file, lease_path);

  struct stat before {};
  LMDJ_CHECK(::stat(protected_file.c_str(), &before) == 0);
  LMDJ_CHECK(before.st_nlink == 2);
  auto platform = make_native_project_storage_platform(metadata_root);
  const auto rejected = platform->acquire_writer(bundle);

  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_project);
  struct stat after {};
  LMDJ_CHECK(::stat(protected_file.c_str(), &after) == 0);
  LMDJ_CHECK((after.st_mode & 0777) == 0640);
  LMDJ_CHECK(after.st_dev == before.st_dev);
  LMDJ_CHECK(after.st_ino == before.st_ino);
  LMDJ_CHECK(after.st_nlink == 2);
}

void test_complete_immutable_append_replace_and_remove_contract() {
  TempDirectory temp;
  const auto directory = temp.path() / "files";
  const auto path = directory / "payload.bin";
  auto platform = make_default_project_storage_platform();
  LMDJ_CHECK(platform->ensure_directory(directory).has_value());
  auto lease = platform->acquire_writer(temp.path());
  LMDJ_CHECK(lease.has_value());

  const auto initial = bytes("alpha\n");
  LMDJ_CHECK(platform->create_immutable(path, initial).has_value());
  LMDJ_CHECK(platform->exists(path).value());
  LMDJ_CHECK(platform->byte_length(path).value() == initial.size());
  LMDJ_CHECK(text(platform->read_complete(path).value()) == "alpha\n");

  const auto collision = platform->create_immutable(path, bytes("other"));
  LMDJ_CHECK(!collision.has_value());
  LMDJ_CHECK(collision.error().code == ErrorCode::io_error);
  LMDJ_CHECK(
      collision.error().details.at("storage_condition") == "already_exists");
  LMDJ_CHECK(text(platform->read_complete(path).value()) == "alpha\n");

  LMDJ_CHECK(
      platform->append_durable(path, initial.size(), bytes("beta\n"))
          .has_value());
  LMDJ_CHECK(text(platform->read_complete(path).value()) == "alpha\nbeta\n");

  const auto torn_path = directory / "torn.jsonl";
  LMDJ_CHECK(
      platform->create_immutable(torn_path, bytes("alpha\npartial")).has_value());
  LMDJ_CHECK(
      platform->append_durable(torn_path, 6, bytes("beta\n")).has_value());
  LMDJ_CHECK(text(platform->read_complete(torn_path).value()) == "alpha\nbeta\n");

  LMDJ_CHECK(platform->replace_complete(path, bytes("published\n")).has_value());
  LMDJ_CHECK(text(platform->read_complete(path).value()) == "published\n");
  const auto names_after_replace = platform->list_names(directory);
  LMDJ_CHECK(names_after_replace.has_value());
  const std::vector<std::string> expected_names{"payload.bin", "torn.jsonl"};
  LMDJ_CHECK(names_after_replace.value() == expected_names);

  LMDJ_CHECK(platform->remove(path).has_value());
  LMDJ_CHECK(!platform->exists(path).value());
  LMDJ_CHECK(platform->remove(path).has_value());
}

void test_append_obeys_supplied_binary_prefix_and_flushes_once() {
  TempDirectory temp;
  const auto bundle = temp.path() / "binary-append.lmdj";
  const auto directory = bundle / "recovery/active";
  const auto path =
      directory / "00000000-0000-4000-8000-000000000001.jsonl";
  auto platform = make_default_project_storage_platform();
  LMDJ_CHECK(platform->ensure_directory(directory).has_value());
  auto lease = platform->acquire_writer(bundle);
  LMDJ_CHECK(lease.has_value());

  const std::vector<std::byte> initial{
      std::byte{0x41},
      std::byte{0x0a},
      std::byte{0x42},
      std::byte{0x00},
      std::byte{0xff},
  };
  const std::vector<std::byte> appended{
      std::byte{0xde},
      std::byte{0xad},
  };
  LMDJ_CHECK(platform->create_immutable(path, initial).has_value());

  active_journal_sync_calls = 0;
  lmdj::foundation::Result<void> result =
      lmdj::foundation::Result<void>::failure(
          lmdj::foundation::Error{
              ErrorCode::internal_error,
              "binary append did not run",
          });
  {
    StorageHookGuard hook(count_active_journal_sync);
    result = platform->append_durable(path, 3, appended);
  }

  LMDJ_CHECK(result.has_value());
  LMDJ_CHECK(active_journal_sync_calls == 1);
  const std::vector<std::byte> expected{
      std::byte{0x41},
      std::byte{0x0a},
      std::byte{0x42},
      std::byte{0xde},
      std::byte{0xad},
  };
  LMDJ_CHECK(platform->read_complete(path).value() == expected);

  const auto before_rejected_append = platform->read_complete(path).value();
  active_journal_sync_calls = 0;
  lmdj::foundation::Result<void> rejected =
      lmdj::foundation::Result<void>::success();
  {
    StorageHookGuard hook(count_active_journal_sync);
    rejected = platform->append_durable(
        path,
        static_cast<std::uint64_t>(before_rejected_append.size()) + 1,
        std::vector<std::byte>{std::byte{0xee}});
  }
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::io_error);
  LMDJ_CHECK(active_journal_sync_calls == 0);
  LMDJ_CHECK(platform->read_complete(path).value() == before_rejected_append);
}

void test_immutable_fault_phases_precede_atomic_publication() {
  TempDirectory temp;
  const auto directory = temp.path() / "history/transactions";
  auto platform = make_default_project_storage_platform();
  LMDJ_CHECK(platform->ensure_directory(directory).has_value());
  auto lease = platform->acquire_writer(temp.path());
  LMDJ_CHECK(lease.has_value());
  const auto payload = bytes("complete immutable transaction\n");
  expected_final =
      directory / "1-00000000-0000-4000-8000-000000000001.json";
  expected_size = payload.size();

  expected_fault = FaultPoint::transaction_temp_sync;
  {
    StorageFaultGuard guard;
    const auto failed = platform->create_immutable(expected_final, payload);
    LMDJ_CHECK(!failed.has_value());
    LMDJ_CHECK(fault_calls == 1);
    LMDJ_CHECK(fault_phase_is_exact);
  }
  LMDJ_CHECK(!std::filesystem::exists(expected_final));
  LMDJ_CHECK(!observed_sibling.empty());
  LMDJ_CHECK(!std::filesystem::exists(observed_sibling));

  write_bytes(observed_sibling, "stale-crash-residue");
  const auto stale_sibling = observed_sibling;
  LMDJ_CHECK(std::filesystem::is_regular_file(stale_sibling));
  LMDJ_CHECK(platform->create_immutable(expected_final, payload).has_value());
  LMDJ_CHECK(platform->read_complete(expected_final).value() == payload);
  LMDJ_CHECK(std::filesystem::is_regular_file(stale_sibling));
  LMDJ_CHECK(platform->remove(expected_final).has_value());
  std::filesystem::remove(stale_sibling);

  expected_fault = FaultPoint::transaction_publish;
  {
    StorageFaultGuard guard;
    const auto failed = platform->create_immutable(expected_final, payload);
    LMDJ_CHECK(!failed.has_value());
    LMDJ_CHECK(fault_calls == 1);
    LMDJ_CHECK(fault_phase_is_exact);
  }
  LMDJ_CHECK(!std::filesystem::exists(expected_final));
  LMDJ_CHECK(!observed_sibling.empty());
  LMDJ_CHECK(!std::filesystem::exists(observed_sibling));

  LMDJ_CHECK(platform->create_immutable(expected_final, payload).has_value());
  LMDJ_CHECK(platform->read_complete(expected_final).value() == payload);
}

void test_path_substitution_never_publishes_a_symlink() {
  TempDirectory temp;
  const auto transaction_directory = temp.path() / "history/transactions";
  const auto transaction =
      transaction_directory /
      "1-00000000-0000-4000-8000-000000000001.json";
  const auto manifest = temp.path() / "manifest.json";
  const auto external = temp.path() / "external.bin";
  substitution_target = external;
  write_bytes(external, "external-must-survive");
  auto platform = make_default_project_storage_platform();
  LMDJ_CHECK(platform->ensure_directory(transaction_directory).has_value());
  auto lease = platform->acquire_writer(temp.path());
  LMDJ_CHECK(lease.has_value());

  lmdj::foundation::Result<void> created =
      lmdj::foundation::Result<void>::success();
  {
    StorageHookGuard hook(substitute_storage_sibling);
    created = platform->create_immutable(transaction, bytes("transaction\n"));
  }
  LMDJ_CHECK(!created.has_value());
  LMDJ_CHECK(!std::filesystem::exists(transaction));
  LMDJ_CHECK(std::filesystem::is_regular_file(external));
  LMDJ_CHECK(text(platform->read_complete(external).value()) ==
             "external-must-survive");

  LMDJ_CHECK(
      platform->create_immutable(manifest, bytes("old-manifest\n")).has_value());
  lmdj::foundation::Result<void> replaced =
      lmdj::foundation::Result<void>::success();
  {
    StorageHookGuard hook(substitute_storage_sibling);
    replaced = platform->replace_complete(manifest, bytes("new-manifest\n"));
  }
  LMDJ_CHECK(!replaced.has_value());
  LMDJ_CHECK(!std::filesystem::is_symlink(manifest));
  LMDJ_CHECK(text(platform->read_complete(manifest).value()) ==
             "old-manifest\n");
  LMDJ_CHECK(text(platform->read_complete(external).value()) ==
             "external-must-survive");
}

void test_names_use_unsigned_byte_order() {
  TempDirectory temp;
  const auto directory = temp.path() / "names";
  auto platform = make_default_project_storage_platform();
  LMDJ_CHECK(platform->ensure_directory(directory).has_value());
  auto lease = platform->acquire_writer(temp.path());
  LMDJ_CHECK(lease.has_value());
  const std::vector<std::string> unsorted{
      std::string{"\xF0\x9F\x98\x80-file"},
      std::string{"\xE2\x82\xAC-file"},
      std::string{"\xC2\xA2-file"},
      "z-file",
      "A-file",
  };
  for (const auto& name : unsorted) {
    LMDJ_CHECK(
        platform->create_immutable(directory / name, bytes(name)).has_value());
  }

  const auto names = platform->list_names(directory);
  LMDJ_CHECK(names.has_value());
  const std::vector<std::string> expected{
      "A-file",
      "z-file",
      std::string{"\xC2\xA2-file"},
      std::string{"\xE2\x82\xAC-file"},
      std::string{"\xF0\x9F\x98\x80-file"},
  };
  LMDJ_CHECK(names.value() == expected);

  const auto ignored_directory = directory / "ignored-directory";
  LMDJ_CHECK(platform->ensure_directory(ignored_directory).has_value());
  LMDJ_CHECK(platform->list_names(directory).value() == expected);
}

void test_directory_transfer_primitives_are_atomic_and_path_safe() {
  TempDirectory temp;
  const auto root = temp.path() / "directory-transfer";
  auto platform = make_default_project_storage_platform();
  LMDJ_CHECK(platform->ensure_directory(root / "z-directory").has_value());
  LMDJ_CHECK(platform->ensure_directory(root / "A-directory").has_value());
  LMDJ_CHECK(
      platform->ensure_directory(root / "\xC2\xA2-directory").has_value());
  auto lease = platform->acquire_writer(root);
  LMDJ_CHECK(lease.has_value());
  LMDJ_CHECK(
      platform->create_immutable(root / "ignored.bin", bytes("file"))
          .has_value());

  const std::vector<std::string> expected_directories{
      "A-directory",
      "z-directory",
      std::string{"\xC2\xA2-directory"},
  };
  LMDJ_CHECK(
      platform->list_directories(root).value() == expected_directories);

  const auto staging = root / "staging";
  const auto destination = root / "published";
  LMDJ_CHECK(platform->ensure_directory(staging / "nested").has_value());
  LMDJ_CHECK(
      platform->create_immutable(
          staging / "nested/payload.bin", bytes("complete"))
          .has_value());
  LMDJ_CHECK(
      platform->publish_directory_if_absent(staging, destination)
          .has_value());
  LMDJ_CHECK(!platform->directory_exists(staging).value());
  LMDJ_CHECK(platform->directory_exists(destination).value());
  LMDJ_CHECK(
      text(platform->read_complete(destination / "nested/payload.bin").value()) ==
      "complete");

  const auto collision_staging = root / "collision-staging";
  LMDJ_CHECK(platform->ensure_directory(collision_staging).has_value());
  LMDJ_CHECK(
      platform->create_immutable(
          collision_staging / "payload.bin", bytes("must-survive"))
          .has_value());
  const auto collision = platform->publish_directory_if_absent(
      collision_staging, destination);
  LMDJ_CHECK(!collision.has_value());
  LMDJ_CHECK(collision.error().code == ErrorCode::io_error);
  LMDJ_CHECK(
      collision.error().details.at("storage_condition") ==
      "already_exists");
  LMDJ_CHECK(platform->directory_exists(collision_staging).value());
  LMDJ_CHECK(
      text(platform->read_complete(destination / "nested/payload.bin").value()) ==
      "complete");

  const auto external = temp.path() / "external";
  std::filesystem::create_directories(external);
  write_bytes(external / "survive.bin", "external");
  const auto unsafe = root / "unsafe";
  LMDJ_CHECK(platform->ensure_directory(unsafe).has_value());
  std::filesystem::create_directory_symlink(external, unsafe / "escape");
  const auto unsafe_remove = platform->remove_tree(unsafe);
  LMDJ_CHECK(!unsafe_remove.has_value());
  LMDJ_CHECK(unsafe_remove.error().code == ErrorCode::invalid_project);
  LMDJ_CHECK(std::filesystem::is_regular_file(external / "survive.bin"));
  std::filesystem::remove(unsafe / "escape");

  LMDJ_CHECK(platform->remove_tree(destination).has_value());
  LMDJ_CHECK(!platform->directory_exists(destination).value());
  LMDJ_CHECK(platform->remove_tree(destination).has_value());
  LMDJ_CHECK(platform->remove_tree(collision_staging).has_value());
}

void test_replacement_readers_observe_only_complete_versions() {
  TempDirectory temp;
  const auto directory = temp.path() / "atomic";
  const auto path = directory / "pointer.json";
  auto platform = make_default_project_storage_platform();
  LMDJ_CHECK(platform->ensure_directory(directory).has_value());
  auto lease = platform->acquire_writer(temp.path());
  LMDJ_CHECK(lease.has_value());
  const std::vector<std::byte> first(256U * 1024U, std::byte{'a'});
  const std::vector<std::byte> second(256U * 1024U, std::byte{'b'});
  LMDJ_CHECK(platform->create_immutable(path, first).has_value());

  std::atomic<bool> started{false};
  std::atomic<bool> stopped{false};
  auto reader = std::async(
      std::launch::async,
      [&]() {
        started.store(true, std::memory_order_release);
        while (!stopped.load(std::memory_order_acquire)) {
          const auto observed = platform->read_complete(path);
          LMDJ_CHECK(observed.has_value());
          LMDJ_CHECK(
              observed.value() == first || observed.value() == second);
        }
      });
  while (!started.load(std::memory_order_acquire)) {
    std::this_thread::yield();
  }
  for (std::size_t index = 0; index < 32; ++index) {
    const auto& replacement = index % 2 == 0 ? second : first;
    LMDJ_CHECK(platform->replace_complete(path, replacement).has_value());
  }
  stopped.store(true, std::memory_order_release);
  reader.get();
}

void test_complete_read_serializes_compliant_same_inode_mutation() {
  using namespace std::chrono_literals;
  TempDirectory temp;
  const auto directory = temp.path() / "stable-read";
  const auto path = directory / "payload.bin";
  auto platform = make_default_project_storage_platform();
  LMDJ_CHECK(platform->ensure_directory(directory).has_value());
  auto lease = platform->acquire_writer(temp.path());
  LMDJ_CHECK(lease.has_value());
  const std::vector<std::byte> before(512U * 1024U, std::byte{'a'});
  const std::vector<std::byte> after(512U * 1024U, std::byte{'b'});
  LMDJ_CHECK(platform->create_immutable(path, before).has_value());

  const int descriptor = ::open(path.c_str(), O_RDWR | O_CLOEXEC);
  LMDJ_CHECK(descriptor >= 0);
  LMDJ_CHECK(::flock(descriptor, LOCK_EX) == 0);
  const auto first_half = after.size() / 2;
  LMDJ_CHECK(
      ::pwrite(descriptor, after.data(), first_half, 0) ==
      static_cast<ssize_t>(first_half));

  auto reader = std::async(
      std::launch::async,
      [platform, path]() { return platform->read_complete(path); });
  const auto status_while_locked = reader.wait_for(150ms);
  LMDJ_CHECK(
      ::pwrite(
          descriptor,
          after.data() + first_half,
          after.size() - first_half,
          static_cast<off_t>(first_half)) ==
      static_cast<ssize_t>(after.size() - first_half));
  LMDJ_CHECK(::fsync(descriptor) == 0);
  LMDJ_CHECK(::flock(descriptor, LOCK_UN) == 0);
  LMDJ_CHECK(::close(descriptor) == 0);

  const auto observed = reader.get();
  LMDJ_CHECK(status_while_locked == std::future_status::timeout);
  LMDJ_CHECK(observed.has_value());
  LMDJ_CHECK(observed.value() == after);
}

void test_special_files_are_rejected_without_blocking() {
  using namespace std::chrono_literals;
  TempDirectory temp;
  const auto directory = temp.path() / "special";
  const auto fifo = directory / "payload.fifo";
  auto platform = make_default_project_storage_platform();
  LMDJ_CHECK(platform->ensure_directory(directory).has_value());
  auto lease = platform->acquire_writer(temp.path());
  LMDJ_CHECK(lease.has_value());
  LMDJ_CHECK(::mkfifo(fifo.c_str(), 0600) == 0);

  auto reader = std::async(
      std::launch::async,
      [platform, fifo]() { return platform->read_complete(fifo); });
  const auto status = reader.wait_for(250ms);
  if (status != std::future_status::ready) {
    const int writer = ::open(fifo.c_str(), O_WRONLY | O_NONBLOCK | O_CLOEXEC);
    LMDJ_CHECK(writer >= 0);
    LMDJ_CHECK(::close(writer) == 0);
  }
  const auto rejected = reader.get();
  LMDJ_CHECK(status == std::future_status::ready);
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::io_error);
  const auto managed_tree = platform->validate_managed_tree(directory);
  LMDJ_CHECK(!managed_tree.has_value());
  LMDJ_CHECK(managed_tree.error().code == ErrorCode::invalid_project);
}

void test_managed_tree_rejects_hard_linked_regular_files() {
  TempDirectory temp;
  const auto managed = temp.path() / "hard-linked-tree";
  const auto payload = managed / "payload.bin";
  const auto alias = managed / "alias.bin";
  std::filesystem::create_directories(managed);
  write_bytes(payload, "project");
  std::filesystem::create_hard_link(payload, alias);

  struct stat metadata {};
  LMDJ_CHECK(::stat(payload.c_str(), &metadata) == 0);
  LMDJ_CHECK(metadata.st_nlink == 2);

  auto platform = make_default_project_storage_platform();
  const auto rejected = platform->validate_managed_tree(managed);
  LMDJ_CHECK(!rejected.has_value());
  LMDJ_CHECK(rejected.error().code == ErrorCode::invalid_project);
}

void test_symlinks_are_rejected_and_system_failures_are_typed() {
  TempDirectory temp;
  const auto managed = temp.path() / "managed";
  const auto external = temp.path() / "external.bin";
  const auto linked = managed / "linked.bin";
  auto platform = make_default_project_storage_platform();
  LMDJ_CHECK(platform->ensure_directory(managed).has_value());
  auto lease = platform->acquire_writer(temp.path());
  LMDJ_CHECK(lease.has_value());
  LMDJ_CHECK(
      platform->create_immutable(external, bytes("external")).has_value());
  std::filesystem::create_symlink(external, linked);

  const auto tree = platform->validate_managed_tree(managed);
  LMDJ_CHECK(!tree.has_value());
  LMDJ_CHECK(tree.error().code == ErrorCode::invalid_project);
  const auto read_link = platform->read_complete(linked);
  LMDJ_CHECK(!read_link.has_value());
  LMDJ_CHECK(read_link.error().code == ErrorCode::invalid_project);

  const auto external_directory = temp.path() / "external-directory";
  std::filesystem::create_directory(external_directory);
  const auto linked_directory = temp.path() / "linked-directory";
  std::filesystem::create_directory_symlink(
      external_directory,
      linked_directory);
  const auto missing_through_link = linked_directory / "missing.bin";
  const auto missing_exists = platform->exists(missing_through_link);
  LMDJ_CHECK(!missing_exists.has_value());
  LMDJ_CHECK(missing_exists.error().code == ErrorCode::invalid_project);
  const auto missing_tree =
      platform->validate_managed_tree(missing_through_link);
  LMDJ_CHECK(!missing_tree.has_value());
  LMDJ_CHECK(missing_tree.error().code == ErrorCode::invalid_project);

  const auto directory_read = platform->read_complete(managed);
  LMDJ_CHECK(!directory_read.has_value());
  LMDJ_CHECK(directory_read.error().code == ErrorCode::io_error);
  LMDJ_CHECK(
      directory_read.error().details.at("path") == managed.generic_string());
  LMDJ_CHECK(directory_read.error().details.contains("system_error"));
}

}  // namespace

int main() {
  try {
    test_writer_lease_is_reentrant_per_platform_and_competes_across_instances();
    test_writer_lease_rejects_hard_link_before_changing_permissions();
    test_complete_immutable_append_replace_and_remove_contract();
    test_append_obeys_supplied_binary_prefix_and_flushes_once();
    test_immutable_fault_phases_precede_atomic_publication();
    test_path_substitution_never_publishes_a_symlink();
    test_names_use_unsigned_byte_order();
    test_directory_transfer_primitives_are_atomic_and_path_safe();
    test_replacement_readers_observe_only_complete_versions();
    test_complete_read_serializes_compliant_same_inode_mutation();
    test_special_files_are_rejected_without_blocking();
    test_managed_tree_rejects_hard_linked_regular_files();
    test_symlinks_are_rejected_and_system_failures_are_typed();
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
  std::cout << "project storage platform tests: PASS\n";
  return 0;
}
