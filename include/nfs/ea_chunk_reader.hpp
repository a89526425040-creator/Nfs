#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <string>
#include <vector>
#include <utility>

namespace nfs::formats {

struct Chunk {
    std::uint32_t id{};
    std::uint32_t payload_size{};
    std::size_t header_offset{};
    std::size_t payload_offset{};
    std::size_t end_offset{};
    std::size_t depth{};
    std::optional<std::size_t> parent_index;
    bool container{};
};

struct Padding {
    std::size_t offset{};
    std::size_t size{};
    std::size_t depth{};
};

struct ScanError {
    std::size_t offset{};
    std::string message;
};

struct ScanResult {
    std::vector<Chunk> chunks;
    std::vector<Padding> padding;
    std::optional<ScanError> error;

    [[nodiscard]] bool ok() const noexcept { return !error.has_value(); }
};

namespace detail {

inline std::uint32_t read_u32le(std::span<const std::byte> bytes,
                                std::size_t offset) noexcept {
    return std::to_integer<std::uint32_t>(bytes[offset]) |
           (std::to_integer<std::uint32_t>(bytes[offset + 1]) << 8U) |
           (std::to_integer<std::uint32_t>(bytes[offset + 2]) << 16U) |
           (std::to_integer<std::uint32_t>(bytes[offset + 3]) << 24U);
}

inline bool is_padding(std::span<const std::byte> bytes,
                       std::size_t begin, std::size_t end) noexcept {
    for (std::size_t i = begin; i < end; ++i) {
        const auto value = std::to_integer<unsigned int>(bytes[i]);
        if (value != 0U && value != 0x11U) {
            return false;
        }
    }
    return true;
}

inline void fail(ScanResult& result, std::size_t offset,
                 std::string message) {
    if (!result.error) {
        result.error = ScanError{offset, std::move(message)};
    }
}

inline void walk(std::span<const std::byte> bytes,
                 std::size_t begin, std::size_t end,
                 std::size_t depth, std::size_t max_depth,
                 std::optional<std::size_t> parent,
                 ScanResult& result) {
    std::size_t pos = begin;
    while (pos < end && !result.error) {
        const std::size_t remaining = end - pos;
        if (remaining < 8U) {
            if (is_padding(bytes, pos, end)) {
                result.padding.push_back(Padding{pos, remaining, depth});
            } else {
                fail(result, pos, "non-padding trailing bytes shorter than chunk header");
            }
            return;
        }

        const std::uint32_t id = read_u32le(bytes, pos);
        const std::uint32_t size = read_u32le(bytes, pos + 4U);
        if (id == 0U) {
            if (static_cast<std::size_t>(size) > remaining - 8U) {
                if (is_padding(bytes, pos, end)) {
                    result.padding.push_back(Padding{pos, remaining, depth});
                } else {
                    fail(result, pos, "zero-ID padding chunk exceeds parent boundary");
                }
                return;
            }
            const std::size_t total = 8U + static_cast<std::size_t>(size);
            result.padding.push_back(Padding{pos, total, depth});
            pos += total;
            continue;
        }

        if (id == 0x11111111U) {
            std::size_t run_end = pos;
            while (run_end < end && bytes[run_end] == std::byte{0x11}) {
                ++run_end;
            }
            result.padding.push_back(Padding{pos, run_end - pos, depth});
            pos = run_end;
            continue;
        }

        const std::size_t payload = pos + 8U;
        const std::size_t payload_size = static_cast<std::size_t>(size);
        if (payload_size > end - payload) {
            fail(result, pos, "chunk payload exceeds immediate parent boundary");
            return;
        }
        const std::size_t chunk_end = payload + payload_size;
        const bool container = (id >> 28U) == 0x8U;
        const std::size_t index = result.chunks.size();
        result.chunks.push_back(Chunk{
            id, size, pos, payload, chunk_end, depth, parent, container
        });

        if (container) {
            if (depth >= max_depth) {
                fail(result, pos, "maximum nested-container depth exceeded");
                return;
            }
            walk(bytes, payload, chunk_end, depth + 1U, max_depth, index, result);
        }
        pos = chunk_end;
    }
}

}  // namespace detail

// The high-nibble container rule is intentionally isolated here. It is a
// format-family rule under validation against the PS2 retail resources.
inline ScanResult scan_chunks(std::span<const std::byte> bytes,
                              std::size_t max_depth = 24U) {
    ScanResult result;
    if (max_depth == 0U) {
        result.error = ScanError{0U, "max_depth must be positive"};
        return result;
    }
    detail::walk(bytes, 0U, bytes.size(), 0U, max_depth, std::nullopt, result);
    return result;
}

}  // namespace nfs::formats
