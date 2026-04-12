cmake_minimum_required(VERSION 3.22.1)
project("native-lib")

add_library(native-lib SHARED native-lib.cpp)

find_library(log-lib log)

target_link_options(native-lib PRIVATE -Wl,-z,max-page-size=16384)

target_link_libraries(native-lib ${log-lib})
