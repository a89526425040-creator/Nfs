#include "os.h"

#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>

int g_trace = 0;
double g_run_seconds = 0.0;
extern const EEFuncEntry g_ee_funcs[] = {{0, nullptr, nullptr}};
extern const size_t g_ee_nfuncs = 0;

namespace {
std::ofstream g_packets;
std::ofstream g_segments;
uint64_t g_packet_offset = 0;

void capture(int path, const uint8_t* data, uint32_t qwc) {
    const size_t bytes = static_cast<size_t>(qwc) * 16;
    if (bytes) {
        g_packets.write(reinterpret_cast<const char*>(data), static_cast<std::streamsize>(bytes));
        if (!g_packets) rt_die("cannot write GIF packet capture");
    }
    g_segments << path << '\t' << qwc << '\t' << g_packet_offset << '\n';
    g_packet_offset += bytes;
}

std::vector<uint8_t> read_all(const std::filesystem::path& path) {
    std::ifstream file(path, std::ios::binary);
    if (!file) rt_die("cannot open VIF stream: %s", path.string().c_str());
    return std::vector<uint8_t>(std::istreambuf_iterator<char>(file), {});
}
}  // namespace

void gs_gif(int path, const uint8_t* data, uint32_t qwc) {
    capture(path, data, qwc);
}

void gs_gif_batch(std::vector<uint8_t>&& data, std::vector<uint32_t>&& segs) {
    size_t at = 0;
    for (uint32_t segment : segs) {
        const int path = static_cast<int>(segment & 3);
        const uint32_t qwc = segment >> 2;
        const size_t bytes = static_cast<size_t>(qwc) * 16;
        if (at + bytes > data.size()) rt_die("GIF batch segment exceeds data buffer");
        capture(path, data.data() + at, qwc);
        at += bytes;
    }
    if (at != data.size()) rt_die("GIF batch has %zu unreferenced bytes", data.size() - at);
}

uint32_t gs_gif_epoch() { return 0; }
void gs_submit_epoch(uint32_t) {}
bool gs_channel_end(int, uint32_t) { return true; }
double hw_now() { return 0.0; }

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "usage: ps2-vu-replay INPUT.VIF OUTPUT_DIR\n";
        return 2;
    }
    const std::filesystem::path input_path(argv[1]);
    const std::filesystem::path output_dir(argv[2]);
    std::filesystem::create_directories(output_dir);
    const std::string dump_dir = output_dir.string();
    setenv("PS2KIT_VIF1_SYNC", "1", 1);
    setenv("PS2KIT_GS_SYNC", "1", 1);
    setenv("PS2KIT_VU1_DUMP", dump_dir.c_str(), 1);

    g_packets.open(output_dir / "gif-packets.bin", std::ios::binary);
    g_segments.open(output_dir / "gif-segments.tsv");
    if (!g_packets || !g_segments) {
        std::cerr << "cannot create GIF capture files\n";
        return 1;
    }

    const auto vif = read_all(input_path);
    vif1_data(vif.data(), vif.size(), false);
    vif1_drain();
    g_packets.close();
    g_segments.close();

    std::cout << "Input VIF bytes: " << vif.size() << "\n";
    std::cout << "Captured GIF bytes: " << g_packet_offset << "\n";
    std::cout << "VIF1 status: " << vif1_status() << "\n";
    return 0;
}
