#!/bin/bash
set -e

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Change to the lambda-layer directory
cd "$SCRIPT_DIR"

# Enable buildx for multi-architecture support (run once)
docker run --privileged --rm tonistiigi/binfmt --install all

# Clean up any existing files
rm -rf python bin lib
rm -f layer.zip

# Build the container with platform specification
docker build --platform linux/amd64 -t diagram-layer .

# Create temporary container
docker create --name temp_container diagram-layer

# Create the required directories
mkdir -p python
mkdir -p bin
mkdir -p lib

# Copy the contents
docker cp temp_container:/opt/python/. python/
docker cp temp_container:/opt/bin/. bin/
docker cp temp_container:/opt/lib/. lib/

# Clean up container
docker rm temp_container

# Verify contents and architectures
echo "Verifying contents and architectures..."
echo "Python packages:"
ls -la python/
echo -e "\nBin contents:"
ls -la bin/
echo -e "\nLib contents:"
ls -la lib/

# Verify dot binary architecture
echo -e "\nDot binary architecture:"
file bin/dot

echo "Verifying dot binary and dependencies..."
cd bin
ldd ./dot
cd ../lib
echo "Checking library dependencies..."
for lib in *; do
  if [ -f "$lib" ] && [ -x "$lib" ]; then
    echo "Checking $lib:"
    ldd "$lib" 2>/dev/null || echo "Not a dynamic executable"
  fi
done
