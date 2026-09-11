#include "usb_transfer_endpoint.hpp"

#ifdef ESP_PLATFORM

#include <algorithm>
#include <cstring>
#include <string>

#include "driver/usb_serial_jtag.h"
#include "esp_random.h"
#include "esp_timer.h"

namespace lmdj::cardputer {
namespace {

std::uint64_t read_u64(const std::byte* bytes) noexcept {
  std::uint64_t value = 0;
  for (std::size_t i = 0; i < 8; ++i)
    value |= static_cast<std::uint64_t>(std::to_integer<std::uint8_t>(bytes[i])) << (8U * i);
  return value;
}

void write_u64(std::byte* bytes, std::uint64_t value) noexcept {
  for (std::size_t i = 0; i < 8; ++i) bytes[i] = std::byte((value >> (8U * i)) & 0xffU);
}

std::uint8_t wire_result(TransferSessionResult result) noexcept {
  switch (result) {
    case TransferSessionResult::accepted:
    case TransferSessionResult::duplicate:
    case TransferSessionResult::committed:
    case TransferSessionResult::aborted: return 0;
    case TransferSessionResult::wrong_state: return 1;
    case TransferSessionResult::stale_session: return 3;
    case TransferSessionResult::bad_request_id: return 4;
    case TransferSessionResult::invalid_transfer: return 6;
    case TransferSessionResult::identity_mismatch: return 9;
    case TransferSessionResult::resource_limit: return 7;
  }
  return 13;
}

std::string hex_digest(const std::array<std::byte, 32>& digest) {
  constexpr char digits[] = "0123456789abcdef";
  std::string result;
  result.resize(64);
  for (std::size_t i = 0; i < digest.size(); ++i) {
    const auto value = std::to_integer<std::uint8_t>(digest[i]);
    result[i * 2] = digits[value >> 4U];
    result[i * 2 + 1] = digits[value & 0x0fU];
  }
  return result;
}

std::uint8_t hex_value(char value) noexcept {
  if (value >= '0' && value <= '9') return static_cast<std::uint8_t>(value - '0');
  if (value >= 'a' && value <= 'f') return static_cast<std::uint8_t>(value - 'a' + 10);
  if (value >= 'A' && value <= 'F') return static_cast<std::uint8_t>(value - 'A' + 10);
  return 0xffU;
}

bool parse_hex_digest(const std::array<char, 64>& text,
                      std::array<std::byte, 32>& digest) noexcept {
  for (std::size_t i = 0; i < digest.size(); ++i) {
    const auto high = hex_value(text[i * 2]);
    const auto low = hex_value(text[i * 2 + 1]);
    if (high > 0x0fU || low > 0x0fU) return false;
    digest[i] = std::byte(static_cast<std::uint8_t>((high << 4U) | low));
  }
  return true;
}

}  // namespace

UsbTransferEndpoint::UsbTransferEndpoint(RuntimeHost& host,
                                         std::size_t maximum_content_bytes) noexcept
    : host_(host),
      session_(maximum_content_bytes, commit_sink, this, nonce_source, nullptr) {}

bool UsbTransferEndpoint::nonce_source(void*, std::array<std::byte, 16>& nonce) noexcept {
  for (std::size_t i = 0; i < nonce.size(); i += sizeof(std::uint32_t)) {
    const auto word = esp_random();
    std::memcpy(nonce.data() + i, &word, sizeof(word));
  }
  return std::any_of(nonce.begin(), nonce.end(), [](std::byte value) {
    return value != std::byte{};
  });
}

bool UsbTransferEndpoint::commit_sink(void* context, std::span<const std::byte> bytes,
                                      const TransferContentIdentity& identity) noexcept {
  auto& endpoint = *static_cast<UsbTransferEndpoint*>(context);
  facade::RuntimeContentIdentity runtime_identity{
      hex_digest(identity.sha256), identity.byte_length};
  return endpoint.host_.load_received(bytes, runtime_identity) == HostResult::ok;
}

bool UsbTransferEndpoint::install() noexcept {
  if (installed_) return true;
  usb_serial_jtag_driver_config_t config{};
  config.rx_buffer_size = static_cast<std::uint32_t>(input_.size());
  config.tx_buffer_size = static_cast<std::uint32_t>(output_.size());
  installed_ = usb_serial_jtag_driver_install(&config) == ESP_OK;
  return installed_;
}

std::uint64_t UsbTransferEndpoint::now_ms() const noexcept {
  return static_cast<std::uint64_t>(esp_timer_get_time() / 1000);
}

void UsbTransferEndpoint::respond(std::uint8_t opcode, std::uint32_t request_id,
                                  std::span<const std::byte> payload) noexcept {
  TransferFrame frame;
  frame.opcode = static_cast<std::uint8_t>(opcode | 0x80U);
  frame.request_id = request_id;
  frame.nonce = session_.nonce();
  frame.payload_size = static_cast<std::uint16_t>(payload.size());
  std::copy(payload.begin(), payload.end(), frame.payload.begin());
  std::size_t written = 0;
  if (encode_transfer_frame(frame, output_, written))
    (void)usb_serial_jtag_write_bytes(output_.data(), written, 0);
}

void UsbTransferEndpoint::respond_result(std::uint8_t opcode, std::uint32_t request_id,
                                         TransferSessionResult result) noexcept {
  const std::array<std::byte, 2> payload{
      std::byte(wire_result(result)), std::byte{}};
  respond(opcode, request_id, payload);
}

void UsbTransferEndpoint::respond_result_with_extra(std::uint8_t opcode,
                                                    std::uint32_t request_id,
                                                    TransferSessionResult result,
                                                    std::span<const std::byte> extra) noexcept {
  if (result != TransferSessionResult::accepted &&
      result != TransferSessionResult::duplicate &&
      result != TransferSessionResult::committed &&
      result != TransferSessionResult::aborted) {
    respond_result(opcode, request_id, result);
    return;
  }
  if (extra.size() > output_.size() - 2) {
    respond_result(opcode, request_id, TransferSessionResult::invalid_transfer);
    return;
  }
  std::array<std::byte, transfer_max_frame> payload{};
  payload[0] = std::byte(wire_result(result));
  std::copy(extra.begin(), extra.end(), payload.begin() + 2);
  respond(opcode, request_id,
          std::span<const std::byte>(payload).first(extra.size() + 2));
}

void UsbTransferEndpoint::handle_frame(const TransferFrame& frame) noexcept {
  const auto opcode = frame.opcode;
  const auto nonce = std::span<const std::byte>(frame.nonce);
  const auto payload = std::span<const std::byte>(frame.payload).first(frame.payload_size);
  if (opcode == static_cast<std::uint8_t>(TransferOpcode::hello)) {
    if (!payload.empty()) {
      respond_result(opcode, frame.request_id, TransferSessionResult::invalid_transfer);
      return;
    }
    const auto result = session_.hello(frame.request_id, nonce);
    if (result == TransferSessionResult::accepted) {
      std::array<std::byte, 4> payload{};
      payload[2] = std::byte(transfer_max_payload & 0xffU);
      payload[3] = std::byte((transfer_max_payload >> 8U) & 0xffU);
      respond(opcode, frame.request_id, payload);
    } else {
      respond_result(opcode, frame.request_id, result);
    }
    return;
  }
  if (opcode == static_cast<std::uint8_t>(TransferOpcode::status)) {
    if (!payload.empty()) {
      respond_result(opcode, frame.request_id, TransferSessionResult::invalid_transfer);
      return;
    }
    const auto status = host_.read_status();
    std::array<std::byte, 14> status_payload{};
    status_payload[0] = std::byte{};
    status_payload[1] = std::byte{};
    status_payload[2] = std::byte(static_cast<std::uint8_t>(status.phase));
    status_payload[3] = std::byte(static_cast<std::uint8_t>(status.error));
    status_payload[4] = std::byte(status.armed ? 1 : 0);
    status_payload[5] = std::byte(status.muted ? 1 : 0);
    status_payload[6] = std::byte(status.volume);
    status_payload[7] = std::byte(status.pad_count);
    write_u64(status_payload.data() + 8, status.content_bytes);
    respond(opcode, frame.request_id, status_payload);
    return;
  }
  if (payload.size() < 16) {
    respond_result(opcode, frame.request_id, TransferSessionResult::invalid_transfer);
    return;
  }
  std::array<std::byte, 16> transfer_id{};
  std::copy_n(payload.begin(), transfer_id.size(), transfer_id.begin());
  TransferSessionResult result = TransferSessionResult::wrong_state;
  switch (static_cast<TransferOpcode>(opcode)) {
    case TransferOpcode::begin: {
      if (payload.size() != 56) break;
      if (!host_.read_status().armed) {
        result = TransferSessionResult::wrong_state;
        break;
      }
      TransferContentIdentity identity;
      identity.transfer_id = transfer_id;
      identity.byte_length = read_u64(payload.data() + 16);
      std::copy_n(payload.begin() + 24, identity.sha256.size(), identity.sha256.begin());
      result = session_.begin(frame.request_id, nonce, transfer_id, identity, now_ms());
      if (result == TransferSessionResult::accepted) received_offset_ = 0;
      if (result == TransferSessionResult::accepted || result == TransferSessionResult::duplicate) {
        std::array<std::byte, 24> extra{};
        std::copy(transfer_id.begin(), transfer_id.end(), extra.begin());
        respond_result_with_extra(opcode, frame.request_id, result, extra);
        return;
      }
      break;
    }
    case TransferOpcode::data:
      if (payload.size() >= 25)
        result = session_.data(frame.request_id, nonce, transfer_id, read_u64(payload.data() + 16),
                               payload.subspan(24), now_ms());
      if (result == TransferSessionResult::accepted) received_offset_ += payload.size() - 24;
      if (result == TransferSessionResult::accepted || result == TransferSessionResult::duplicate) {
        std::array<std::byte, 24> extra{};
        std::copy(transfer_id.begin(), transfer_id.end(), extra.begin());
        write_u64(extra.data() + 16, received_offset_);
        respond_result_with_extra(opcode, frame.request_id, result, extra);
        return;
      }
      break;
    case TransferOpcode::commit:
      if (payload.size() == 16)
        result = session_.commit(frame.request_id, nonce, transfer_id, now_ms());
      if (result == TransferSessionResult::committed) {
        std::array<std::byte, 40> extra{};
        const auto status = host_.read_status();
        std::array<std::byte, 32> digest{};
        if (!parse_hex_digest(status.content_sha256, digest)) {
          respond_result(opcode, frame.request_id, TransferSessionResult::wrong_state);
          return;
        }
        write_u64(extra.data(), status.content_bytes);
        std::copy(digest.begin(), digest.end(), extra.begin() + 8);
        respond_result_with_extra(opcode, frame.request_id, result, extra);
        received_offset_ = 0;
        return;
      }
      break;
    case TransferOpcode::abort:
      if (payload.size() == 16)
        result = session_.abort(frame.request_id, nonce, transfer_id);
      if (result == TransferSessionResult::aborted) received_offset_ = 0;
      break;
    default: break;
  }
  respond_result(opcode, frame.request_id, result);
}

void UsbTransferEndpoint::poll() noexcept {
  if (!installed_ && !install()) return;
  const auto available = usb_serial_jtag_read_bytes(input_.data() + input_size_,
                                                     input_.size() - input_size_, 0);
  if (available > 0) input_size_ += static_cast<std::size_t>(available);
  while (input_size_ != 0) {
    TransferFrame frame;
    std::size_t consumed = 0;
    const auto decoded = decode_transfer_frame(
        std::span<const std::byte>(input_).first(input_size_), frame, consumed);
    if (decoded == FrameDecode::need_more) break;
    if (decoded == FrameDecode::bad_magic) {
      const auto drop = std::min(consumed, input_size_);
      std::move(input_.begin() + static_cast<std::ptrdiff_t>(drop),
                input_.begin() + static_cast<std::ptrdiff_t>(input_size_), input_.begin());
      input_size_ -= drop;
      continue;
    }
    if (decoded != FrameDecode::ready) {
      input_size_ = 0;
      break;
    }
    const auto frame_size = transfer_header_bytes + frame.payload_size + 4;
    handle_frame(frame);
    std::move(input_.begin() + static_cast<std::ptrdiff_t>(frame_size),
              input_.begin() + static_cast<std::ptrdiff_t>(input_size_), input_.begin());
    input_size_ -= frame_size;
  }
  (void)session_.expire(now_ms());
}

}  // namespace lmdj::cardputer

#endif
