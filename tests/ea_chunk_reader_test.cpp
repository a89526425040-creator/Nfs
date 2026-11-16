#include "nfs/ea_chunk_reader.hpp"

#include <array>
#include <cstdlib>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace {

void require(bool condition) {
    if (!condition) {
        std::abort();
    }
}

void append_u32le(std::vector<std::byte>& out, std::uint32_t value) {
    for (unsigned shift = 0; shift < 32; shift += 8) {
        out.push_back(static_cast<std::byte>((value >> shift) & 0xffU));
    }
}

void append_header(std::vector<std::byte>& out,
                   std::uint32_t id, std::uint32_t size) {
    append_u32le(out, id);
    append_u32le(out, size);
}

void test_nested_chunks_and_zero_padding() {
    std::vector<std::byte> leaf;
    append_header(leaf, 0x00134002U, 4U);
    leaf.insert(leaf.end(), {static_cast<std::byte>('D'), static_cast<std::byte>('A'),
                             static_cast<std::byte>('T'), std::byte{'A'}});

    std::vector<std::byte> inner;
    append_header(inner, 0x80134001U, static_cast<std::uint32_t>(leaf.size()));
    inner.insert(inner.end(), leaf.begin(), leaf.end());

    std::vector<std::byte> root_payload;
    append_header(root_payload, 0U, 0U);
    root_payload.insert(root_payload.end(), inner.begin(), inner.end());

    std::vector<std::byte> file;
    append_header(file, 0x80134000U,
                  static_cast<std::uint32_t>(root_payload.size()));
    file.insert(file.end(), root_payload.begin(), root_payload.end());

    const auto result = nfs::formats::scan_chunks(file);
    require(result.ok());
    require(result.chunks.size() == 3U);
    require(result.chunks[0].id == 0x80134000U);
    require(result.chunks[1].id == 0x80134001U);
    require(result.chunks[2].id == 0x00134002U);
    require(result.chunks[2].parent_index == 1U);
    require(result.padding.size() == 1U);
    require(result.padding[0].size == 8U);
}

void test_rejects_payload_outside_parent() {
    std::vector<std::byte> file;
    append_header(file, 0x00134002U, 100U);
    file.push_back(std::byte{0x42});
    const auto result = nfs::formats::scan_chunks(file);
    require(!result.ok());
    require(result.error->offset == 0U);
}

void test_rejects_non_padding_tail() {
    const std::array bytes{std::byte{0x42}, std::byte{0x43}, std::byte{0x44}};
    const auto result = nfs::formats::scan_chunks(bytes);
    require(!result.ok());
}

void test_enforces_depth_limit() {
    std::vector<std::byte> leaf;
    append_header(leaf, 0x80134002U, 0U);
    std::vector<std::byte> root;
    append_header(root, 0x80134000U, static_cast<std::uint32_t>(leaf.size()));
    root.insert(root.end(), leaf.begin(), leaf.end());
    const auto result = nfs::formats::scan_chunks(root, 1U);
    require(!result.ok());
}

}  // namespace

int main() {
    test_nested_chunks_and_zero_padding();
    test_rejects_payload_outside_parent();
    test_rejects_non_padding_tail();
    test_enforces_depth_limit();
    return 0;
}
