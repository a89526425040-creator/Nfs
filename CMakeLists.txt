cmake_minimum_required(VERSION 3.20)
project(nfs_research_core LANGUAGES CXX)

enable_testing()

add_executable(ea_chunk_reader_test tests/ea_chunk_reader_test.cpp)
target_include_directories(ea_chunk_reader_test PRIVATE include)
target_compile_features(ea_chunk_reader_test PRIVATE cxx_std_20)

if(MSVC)
    target_compile_options(ea_chunk_reader_test PRIVATE /W4 /WX)
else()
    target_compile_options(ea_chunk_reader_test PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()

add_test(NAME ea_chunk_reader_test COMMAND ea_chunk_reader_test)
