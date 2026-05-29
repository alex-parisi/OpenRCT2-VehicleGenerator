cmake_minimum_required(VERSION 3.25)
project(openrct2_vehicle_generator_native LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Opt-in clang-tidy: -DENABLE_CLANG_TIDY=ON runs .clang-tidy during the build
# for every target defined below. Off by default so normal/CI builds stay fast.
# Homebrew keeps clang-tidy off PATH, hence the HINTS.
option(ENABLE_CLANG_TIDY "Run clang-tidy as part of the build" OFF)
if(ENABLE_CLANG_TIDY)
    find_program(CLANG_TIDY_EXE NAMES clang-tidy
        HINTS /opt/homebrew/opt/llvm/bin /usr/local/opt/llvm/bin)
    if(CLANG_TIDY_EXE)
        set(CMAKE_CXX_CLANG_TIDY "${CLANG_TIDY_EXE}")
        message(STATUS "clang-tidy enabled: ${CLANG_TIDY_EXE}")
    else()
        message(WARNING "ENABLE_CLANG_TIDY is ON but clang-tidy was not found")
    endif()
endif()

# Embree discovery. Priority:
#   1. An explicit -Dembree_DIR=... (honoured by find_package directly).
#   2. $ENV{EMBREE_ROOT} — set by the wheel-build CI, which downloads Embree's
#      official prebuilt release (the lib/cmake/embree-4.x config lives under it).
#   3. Homebrew on macOS for local dev (/opt/homebrew/lib/cmake/embree-4.x).
if(NOT DEFINED embree_DIR AND DEFINED ENV{EMBREE_ROOT})
    list(PREPEND CMAKE_PREFIX_PATH "$ENV{EMBREE_ROOT}")
endif()
if(APPLE AND NOT DEFINED embree_DIR)
    file(GLOB _brew_embree_cfg "/opt/homebrew/lib/cmake/embree-4*")
    if(_brew_embree_cfg)
        list(GET _brew_embree_cfg 0 embree_DIR)
    endif()
endif()

find_package(embree 4 CONFIG REQUIRED)

set(THREADS_PREFER_PTHREAD_FLAG ON)
find_package(Threads REQUIRED)

set(SRC ${CMAKE_CURRENT_SOURCE_DIR}/src)

# ---------------------------------------------------------------------------
# Core library — all renderer logic, no pybind11 dependency.
# Both the Python module and the test suite link against this.
# PIC is required because _native links it into a shared library.
# ---------------------------------------------------------------------------
add_library(_native_core STATIC
    ${SRC}/Mesh.cpp
    ${SRC}/Palette.cpp
    ${SRC}/RayTrace.cpp
    ${SRC}/Renderer.cpp
)
set_target_properties(_native_core PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(_native_core PUBLIC ${SRC})
target_compile_options(_native_core PRIVATE
    $<$<CXX_COMPILER_ID:MSVC>:/W3>
    $<$<NOT:$<CXX_COMPILER_ID:MSVC>>:-Wall -Wextra -Wno-unused-parameter>
)
target_link_libraries(_native_core PUBLIC embree Threads::Threads)

# ---------------------------------------------------------------------------
# Python extension module (skipped when BUILD_PYTHON_MODULE=OFF, e.g. in the
# dev/test preset where pybind11 is not on the system path).
# ---------------------------------------------------------------------------
option(BUILD_PYTHON_MODULE "Build the pybind11 Python extension module" ON)
if(BUILD_PYTHON_MODULE)
    find_package(pybind11 CONFIG REQUIRED)
    pybind11_add_module(_native MODULE bindings.cpp)
    target_include_directories(_native PRIVATE ${SRC})
    target_compile_options(_native PRIVATE
        $<$<CXX_COMPILER_ID:MSVC>:/W3>
        $<$<NOT:$<CXX_COMPILER_ID:MSVC>>:-Wall -Wextra -Wno-unused-parameter>
    )
    target_link_libraries(_native PRIVATE _native_core)
    install(TARGETS _native LIBRARY DESTINATION openrct2_vehicle_generator)
endif()

# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------
if(BUILD_TESTING)
    enable_testing()
    add_subdirectory(test)
endif()
