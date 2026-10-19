#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <new>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <lmdj/cooker/wav_metadata_inspector.hpp>
#include <lmdj/cooker/wav_reader.hpp>
#include "tests/core/support/test.hpp"

namespace {
using Bytes = std::vector<std::byte>;
using lmdj::cooker::WavMetadata;
using lmdj::cooker::WavMetadataInspector;
using lmdj::foundation::ErrorCode;
thread_local bool count_allocations = false;
thread_local std::size_t allocation_count = 0;

void* allocate(std::size_t size) {
  if (count_allocations) ++allocation_count;
  if (auto* memory = std::malloc(size == 0 ? 1 : size)) return memory;
  throw std::bad_alloc{};
}

class AllocationScope {
 public:
  AllocationScope() { allocation_count = 0; count_allocations = true; }
  ~AllocationScope() { count_allocations = false; }
};

void append(Bytes& bytes, std::string_view text) {
  for (unsigned char ch : text) bytes.push_back(static_cast<std::byte>(ch));
}
void put16(Bytes& bytes, std::size_t at, std::uint16_t n) {
  bytes.at(at) = static_cast<std::byte>(n);
  bytes.at(at + 1) = static_cast<std::byte>(n >> 8);
}
void put32(Bytes& bytes, std::size_t at, std::uint32_t n) {
  for (unsigned int i = 0; i < 4; ++i) bytes.at(at + i) = static_cast<std::byte>(n >> (i * 8));
}
void chunk(Bytes& bytes, std::string_view tag, std::span<const std::byte> data, bool padding = true) {
  append(bytes, tag);
  const auto at = bytes.size(); bytes.resize(at + 4); put32(bytes, at, static_cast<std::uint32_t>(data.size()));
  bytes.insert(bytes.end(), data.begin(), data.end());
  if (padding && data.size() % 2) bytes.push_back(std::byte{0xab});
}
Bytes format(std::uint32_t rate = 48000, std::uint16_t channels = 2) {
  Bytes bytes(16);
  put16(bytes, 0, 1); put16(bytes, 2, channels); put32(bytes, 4, rate);
  put32(bytes, 8, rate * channels * 2); put16(bytes, 12, channels * 2); put16(bytes, 14, 16);
  return bytes;
}
Bytes root() { Bytes bytes; append(bytes, "RIFF"); bytes.resize(8); append(bytes, "WAVE"); return bytes; }
void size_riff(Bytes& bytes) { put32(bytes, 4, static_cast<std::uint32_t>(bytes.size() - 8)); }
Bytes wav(bool data_first = false, bool junk = false) {
  auto bytes = root(); const auto fmt = format(); const Bytes data(32, std::byte{0xff});
  if (data_first) chunk(bytes, "data", data);
  chunk(bytes, "fmt ", fmt);
  if (junk) { const std::array payload{std::byte{1},std::byte{2},std::byte{3}}; chunk(bytes,"JUNK",payload); }
  if (!data_first) chunk(bytes, "data", data);
  size_riff(bytes); return bytes;
}
void metadata(const WavMetadata& value, std::uint32_t rate = 48000,
              std::uint16_t channels = 2, std::uint64_t frames = 8) {
  LMDJ_CHECK(value.sample_rate == rate);
  LMDJ_CHECK(value.channels == channels);
  LMDJ_CHECK(value.source_frames == frames);
}

void test_full_span_metadata_never_allocates_decoded_pcm() {
  const auto bytes = wav();
  const auto result = [&] {
    AllocationScope allocations;
    return lmdj::cooker::inspect_wav(bytes);
  }();
  LMDJ_CHECK(result.has_value());
  metadata(result.value());
  LMDJ_CHECK(allocation_count == 0);
}

void test_every_split_and_reused_one_byte_windows() {
  for (bool data_first : {false,true}) for (bool junk : {false,true}) {
    const auto bytes = wav(data_first,junk);
    for (std::size_t split = 0; split <= bytes.size(); ++split) {
      WavMetadataInspector inspector{bytes.size()};
      LMDJ_CHECK(inspector.feed(std::span{bytes}.first(split)).has_value());
      LMDJ_CHECK(inspector.feed({}).has_value());
      LMDJ_CHECK(inspector.feed(std::span{bytes}.subspan(split)).has_value());
      const auto result=inspector.finish(); LMDJ_CHECK(result.has_value()); metadata(result.value());
      LMDJ_CHECK(inspector.finish().has_value());
    }
    WavMetadataInspector inspector{bytes.size()};
    for (const auto byte : bytes) {
      std::array window{byte};
      LMDJ_CHECK(inspector.feed(window).has_value());
      window[0]=std::byte{0};
      LMDJ_CHECK(inspector.feed({}).has_value());
    }
    const auto result=inspector.finish(); LMDJ_CHECK(result.has_value()); metadata(result.value());
  }
}

void test_all_locked_fixtures_against_decoder_and_literal_oracles() {
  // Authoritative producer: make_fixtures.py's accepted_fixtures and sample
  // counts. These values are independent of both C++ implementations.
  struct Oracle { std::string_view name; WavMetadata expected; };
  constexpr std::array<Oracle,7> oracles{{
      {"kick.wav", {48000,1,4800}},
      {"snare.wav", {48000,1,2400}},
      {"mono-44100.wav", {44100,1,8}},
      {"mono-44100-over-web-frame-limit.wav", {44100,1,240001}},
      {"stereo-44100.wav", {44100,2,2}},
      {"stereo.wav", {48000,2,4}},
      {"web-runtime-host-short.wav", {48000,1,240}},
  }};
  std::size_t count=0, literal_count=0;
  for (const auto& file : std::filesystem::directory_iterator("tests/fixtures/audio")) {
    if(file.path().extension()!=".wav") continue;
    std::ifstream stream(file.path(),std::ios::binary);
    LMDJ_CHECK(stream.is_open());
    const std::vector<char> input{std::istreambuf_iterator<char>{stream},std::istreambuf_iterator<char>{}};
    LMDJ_CHECK(!stream.bad());
    Bytes bytes;for(unsigned char byte:input) bytes.push_back(static_cast<std::byte>(byte));
    const auto decoded=lmdj::cooker::decode_wav(bytes);
    WavMetadataInspector inspector{bytes.size()};
    for(std::size_t at=0;at<bytes.size();at+=4093) {
      (void)inspector.feed(std::span{bytes}.subspan(at,std::min<std::size_t>(4093,bytes.size()-at)));
    }
    const auto result=inspector.finish();
    LMDJ_CHECK(result.has_value()==decoded.has_value());
    const auto name=file.path().filename().string();
    const auto oracle=std::find_if(oracles.begin(),oracles.end(),[&](const auto& item) {
      return item.name==name;
    });
    if(decoded.has_value()) {
      metadata(result.value(),decoded.value()->sample_rate,decoded.value()->channels,
          decoded.value()->interleaved.size()/decoded.value()->channels);
      LMDJ_CHECK(oracle!=oracles.end());
      metadata(result.value(),oracle->expected.sample_rate,oracle->expected.channels,
          oracle->expected.source_frames);
      ++literal_count;
    } else {
      LMDJ_CHECK(oracle==oracles.end());
      LMDJ_CHECK(result.error().code==ErrorCode::unsupported_audio);
      LMDJ_CHECK(result.error().message==decoded.error().message);
    }
    ++count;
  }
  LMDJ_CHECK(count>0);
  LMDJ_CHECK(literal_count==oracles.size());
  // Decoder agreement can share a wrong metadata calculation. Literal stereo
  // checks above and this generated mono oracle constrain that blind spot.
  const auto fmt=format(44100,1); auto bytes=root();chunk(bytes,"fmt ",fmt);
  const std::array<std::byte,18> data{};chunk(bytes,"data",data);size_riff(bytes);
  WavMetadataInspector inspector{bytes.size()}; LMDJ_CHECK(inspector.feed(bytes).has_value());
  const auto result=inspector.finish(); LMDJ_CHECK(result.has_value()); metadata(result.value(),44100,1,9);
}

void reject_every_split(const Bytes& bytes) {
  LMDJ_CHECK(!lmdj::cooker::decode_wav(bytes).has_value());
  for(std::size_t split=0;split<=bytes.size();++split) {
    WavMetadataInspector inspector{bytes.size()};
    (void)inspector.feed(std::span{bytes}.first(split));
    (void)inspector.feed(std::span{bytes}.subspan(split));
    const auto result=inspector.finish();
    LMDJ_CHECK(!result.has_value() && result.error().code==ErrorCode::unsupported_audio);
  }
}

void test_malformed_grammar_at_all_boundaries() {
  const auto good=wav();
  for(auto at: {0U,8U}) {auto bytes=good;bytes[at]=std::byte{'X'};reject_every_split(bytes);}
  {auto bytes=good;put32(bytes,4,static_cast<std::uint32_t>(bytes.size()-9));reject_every_split(bytes);}
  {auto bytes=good;put32(bytes,40,1000);reject_every_split(bytes);}
  {auto bytes=good;chunk(bytes,"fmt ",format());size_riff(bytes);reject_every_split(bytes);}
  {auto bytes=good;const std::array<std::byte,4> data{};chunk(bytes,"data",data);size_riff(bytes);reject_every_split(bytes);}
  {auto bytes=root();Bytes fmt(18);chunk(bytes,"fmt ",fmt);size_riff(bytes);reject_every_split(bytes);}
  {auto bytes=root();chunk(bytes,"fmt ",format());size_riff(bytes);reject_every_split(bytes);}
  {auto bytes=root();const std::array<std::byte,4> data{};chunk(bytes,"data",data);size_riff(bytes);reject_every_split(bytes);}
  for(auto [at,value]:std::array<std::pair<std::size_t,std::uint16_t>,4>{{{20,3},{22,0},{32,1},{34,8}}}) {
    auto bytes=good;put16(bytes,at,value);reject_every_split(bytes);
  }
  for(auto at:{24U,28U}) {auto bytes=good;put32(bytes,at,32000);reject_every_split(bytes);}
  for(std::size_t length:{0U,3U}) {
    auto bytes=root();chunk(bytes,"fmt ",format());const Bytes data(length);chunk(bytes,"data",data);size_riff(bytes);reject_every_split(bytes);
  }
  {auto bytes=good;append(bytes,"short");size_riff(bytes);reject_every_split(bytes);}
  {auto bytes=good;const std::array<std::byte,3> data{};chunk(bytes,"JUNK",data,false);size_riff(bytes);reject_every_split(bytes);}
}

void test_partial_extra_and_sticky_input() {
  const auto bytes=wav();
  for(std::size_t cutoff=0;cutoff<bytes.size();++cutoff) {
    WavMetadataInspector inspector{bytes.size()};
    (void)inspector.feed(std::span{bytes}.first(cutoff));
    const auto result=inspector.finish();
    LMDJ_CHECK(!result.has_value());
    const auto error=result.error();
    const auto later=inspector.feed(std::span{bytes}.subspan(cutoff));
    LMDJ_CHECK(!later.has_value() && later.error().message==error.message);
    LMDJ_CHECK(!inspector.finish().has_value());
  }
  WavMetadataInspector inspector{bytes.size()};
  LMDJ_CHECK(inspector.feed(bytes).has_value() && inspector.finish().has_value());
  const std::array extra{std::byte{0}};
  LMDJ_CHECK(!inspector.feed(extra).has_value());
  LMDJ_CHECK(!inspector.finish().has_value());
  // A huge advertised file is not accepted from a 44-byte header hint.
  auto header=wav(); header.resize(44);put32(header,4,345600036);put32(header,40,345600000);
  WavMetadataInspector hinted{345600044}; LMDJ_CHECK(hinted.feed(header).has_value());
  LMDJ_CHECK(!hinted.finish().has_value());
}

void test_thirty_minute_silence_uses_fixed_window_without_allocations() {
  auto header=root();chunk(header,"fmt ",format());append(header,"data");header.resize(44);
  put32(header,4,345600036);put32(header,40,345600000);
  const std::array<std::byte,65536> window{};
  WavMetadataInspector inspector{345600044};
  const auto result=[&] {
    AllocationScope allocations;
    LMDJ_CHECK(inspector.feed(header).has_value());
    std::uint64_t remaining=345600000;
    while(remaining) {
      const auto size=static_cast<std::size_t>(std::min<std::uint64_t>(remaining,window.size()));
      LMDJ_CHECK(inspector.feed(std::span{window}.first(size)).has_value());
      remaining-=size;
    }
    return inspector.finish();
  }();
  LMDJ_CHECK(result.has_value()); metadata(result.value(),48000,2,86400000);
  LMDJ_CHECK(result.value().source_frames/result.value().sample_rate==1800);
  LMDJ_CHECK(allocation_count==0);
}
}  // namespace

void* operator new(std::size_t size) { return allocate(size); }
void* operator new[](std::size_t size) { return allocate(size); }
void operator delete(void* pointer) noexcept { std::free(pointer); }
void operator delete[](void* pointer) noexcept { std::free(pointer); }
void operator delete(void* pointer,std::size_t) noexcept { std::free(pointer); }
void operator delete[](void* pointer,std::size_t) noexcept { std::free(pointer); }

int main() {
  try {
    test_full_span_metadata_never_allocates_decoded_pcm();
    test_every_split_and_reused_one_byte_windows();
    test_all_locked_fixtures_against_decoder_and_literal_oracles();
    test_malformed_grammar_at_all_boundaries();
    test_partial_extra_and_sticky_input();
    test_thirty_minute_silence_uses_fixed_window_without_allocations();
  } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
  std::cout<<"streaming WAV metadata: PASS\n";
}
