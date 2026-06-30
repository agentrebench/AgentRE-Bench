# Simple Makefile for AgentRE-Bench

# Build all sample binaries
default: build

build:
	./build_binaries.sh

build-windows:
	./build_windows_binaries.sh

build-all: build build-windows

# Run the benchmark with default settings
run:
	python run_benchmark.py --all

# Clean generated binaries and results
clean:
	rm -rf binaries results
