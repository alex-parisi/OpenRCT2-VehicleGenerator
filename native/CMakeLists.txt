cmake_minimum_required(VERSION 3.25)
project(openrct2_vehicle_generator_native LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Homebrew on macOS — `find_package(embree 4 CONFIG)` will then pick up
# /opt/homebrew/lib/cmake/embree-4.x.
if(APPLE AND NOT DEFINED embree_DIR)
    file(GLOB _brew_embree_cfg "/opt/homebrew/lib/cmake/embree-4*")
    if(_brew_embree_cfg)
        list(GET _brew_embree_cfg 0 embree_DIR)
    endif()
endif()

find_package(embree 4 CONFIG REQUIRED)
find_package(pybind11 CONFIG REQUIRED)

set(THREADS_PREFER_PTHREAD_FLAG ON)
find_package(Threads REQUIRED)

set(SRC ${CMAKE_CURRENT_SOURCE_DIR}/src)

pybind11_add_module(_native MODULE
    bindings.cpp
    ${SRC}/VectorMath.cpp
    ${SRC}/Mesh.cpp
    ${SRC}/Palette.cpp
    ${SRC}/RayTrace.cpp
    ${SRC}/Renderer.cpp
)

target_include_directories(_native PRIVATE ${SRC})

target_compile_options(_native PRIVATE
    $<$<CXX_COMPILER_ID:MSVC>:/W3>
    $<$<NOT:$<CXX_COMPILER_ID:MSVC>>:-Wall -Wextra -Wno-unused-parameter>
)

target_link_libraries(_native PRIVATE embree Threads::Threads)

install(TARGETS _native LIBRARY DESTINATION openrct2_vehicle_generator)
