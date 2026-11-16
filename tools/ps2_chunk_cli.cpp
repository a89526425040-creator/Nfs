#include "nfs/ea_chunk_reader.hpp"

#include <cstddef>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
#include <string>
#include <vector>

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "usage: ps2_chunk_cli RESOURCE_FILE\n";
        return 2;
    }

    std::ifstream input(argv[1], std::ios::binary);
    if (!input) {
        std::cerr << "cannot open input file\n";
        return 2;
    }
    std::vector<char> raw((std::istreambuf_iterator<char>(input)),
                          std::istreambuf_iterator<char>());
    std::vector<std::byte> bytes;
    bytes.reserve(raw.size());
    for (unsigned char value : raw) {
        bytes.push_back(static_cast<std::byte>(value));
    }

    const auto result = nfs::formats::scan_chunks(bytes);
    if (!result.ok()) {
        std::cerr << "chunk error at 0x" << std::hex
                  << result.error->offset << ": "
                  << result.error->message << '\n';
        return 1;
    }

    std::map<std::uint32_t, std::size_t> counts;
    std::size_t containers = 0;
    for (const auto& chunk : result.chunks) {
        ++counts[chunk.id];
        containers += chunk.container ? 1U : 0U;
    }

    std::cout << argv[1]
              << ": bytes=" << bytes.size()
              << " chunks=" << result.chunks.size()
              << " containers=" << containers
              << " leaves=" << result.chunks.size() - containers
              << " padding_regions=" << result.padding.size()
              << " padding_bytes=";
    std::size_t padding_bytes = 0;
    for (const auto& item : result.padding) {
        padding_bytes += item.size;
    }
    std::cout << padding_bytes << '\n';
    for (const auto& [id, count] : counts) {
        std::cout << "  0x" << std::hex << id << std::dec << ": " << count << '\n';
    }
    return 0;
}
