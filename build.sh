#!/bin/bash
# Build script for Bifrost Docker images
# Builds production images for bifrost-api and bifrost-client
# Supports multi-architecture builds (AMD64 + ARM64)

set -e

# Defaults
TAG=$(git describe --tags --always --dirty 2>/dev/null || echo "latest")
REGISTRY="ghcr.io/jackmusick"
PUSH=false
BUILD_API=true
BUILD_CLIENT=true
NO_CACHE=""
PLATFORMS="linux/amd64,linux/arm64"
BUILDER_NAME="bifrost-builder"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Build production Docker images for Bifrost"
    echo ""
    echo "Options:"
    echo "  -t, --tag TAG        Version tag (default: latest)"
    echo "  -r, --registry REG   Docker registry/namespace (default: ghcr.io/jackmusick)"
    echo "  -p, --push           Push images to registry after building"
    echo "  --api-only           Build only the API image"
    echo "  --client-only        Build only the client image"
    echo "  --no-cache           Build without Docker cache"
    echo "  --platform PLAT      Target platforms (default: linux/amd64,linux/arm64)"
    echo "  --amd64-only         Build only for AMD64 (faster for cloud deployments)"
    echo "  --arm64-only         Build only for ARM64"
    echo "  -h, --help           Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                           # Build both images with 'latest' tag"
    echo "  $0 -t v1.0.0                 # Build with specific version"
    echo "  $0 -t v1.0.0 -p              # Build and push to Docker Hub"
    echo "  $0 --api-only -t dev         # Build only API image"
    echo "  $0 --no-cache                # Build without cache"
    echo "  $0 --amd64-only -p           # Build only AMD64 and push (for cloud)"
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--tag)
            TAG="$2"
            shift 2
            ;;
        -r|--registry)
            REGISTRY="$2"
            shift 2
            ;;
        -p|--push)
            PUSH=true
            shift
            ;;
        --api-only)
            BUILD_CLIENT=false
            shift
            ;;
        --client-only)
            BUILD_API=false
            shift
            ;;
        --no-cache)
            NO_CACHE="--no-cache"
            shift
            ;;
        --platform)
            PLATFORMS="$2"
            shift 2
            ;;
        --amd64-only)
            PLATFORMS="linux/amd64"
            shift
            ;;
        --arm64-only)
            PLATFORMS="linux/arm64"
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            ;;
    esac
done

# Change to script directory (repository root)
cd "$(dirname "$0")"

echo -e "${GREEN}Bifrost Docker Build${NC}"
echo "Registry: $REGISTRY"
echo "Tag: $TAG"
echo "Platforms: $PLATFORMS"
echo ""

# Setup buildx builder for multi-platform builds
setup_buildx() {
    echo -e "${YELLOW}Setting up Docker Buildx for multi-platform builds...${NC}"

    # Check if builder exists
    if ! docker buildx inspect "$BUILDER_NAME" > /dev/null 2>&1; then
        echo "Creating new buildx builder: $BUILDER_NAME"
        docker buildx create --name "$BUILDER_NAME" --driver docker-container --bootstrap
    fi

    # Use the builder
    docker buildx use "$BUILDER_NAME"
    echo -e "${GREEN}Buildx builder ready${NC}"
    echo ""
}

# Setup buildx
setup_buildx

# Determine build flags based on push
# Note: Multi-platform builds require --push or --load
# --load only works for single platform, so we use --push for multi-platform
if [ "$PUSH" = true ]; then
    BUILD_OUTPUT="--push"
else
    # For local builds without push, we need to handle multi-platform differently
    # If building for multiple platforms without push, we can only output to registry or tarball
    # For simplicity, if not pushing and multiple platforms, we'll build and load the native platform only
    if [[ "$PLATFORMS" == *","* ]]; then
        echo -e "${YELLOW}Warning: Multi-platform builds require --push to store all architectures.${NC}"
        echo -e "${YELLOW}Building for local platform only. Use -p to push multi-arch images.${NC}"
        BUILD_OUTPUT="--load"
        PLATFORMS="linux/$(uname -m | sed 's/x86_64/amd64/' | sed 's/aarch64/arm64/')"
    else
        BUILD_OUTPUT="--load"
    fi
fi

# Build API image
if [ "$BUILD_API" = true ]; then
    API_IMAGE="$REGISTRY/bifrost-api:$TAG"
    echo -e "${YELLOW}Building API image: $API_IMAGE${NC}"
    echo "  Platforms: $PLATFORMS"

    BIFROST_VERSION=$(git describe --tags --always --dirty 2>/dev/null || echo "unknown")
    docker buildx build $NO_CACHE \
        --platform "$PLATFORMS" \
        -t "$API_IMAGE" \
        -f api/Dockerfile \
        --build-arg "BIFROST_VERSION=${BIFROST_VERSION}" \
        $BUILD_OUTPUT \
        .

    echo -e "${GREEN}API image built successfully${NC}"
    echo ""
fi

# Build Client image
if [ "$BUILD_CLIENT" = true ]; then
    BIFROST_VERSION=${BIFROST_VERSION:-$(git describe --tags --always --dirty 2>/dev/null || echo "unknown")}
    CLIENT_IMAGE="$REGISTRY/bifrost-client:$TAG"
    echo -e "${YELLOW}Building Client image: $CLIENT_IMAGE${NC}"
    echo "  Platforms: $PLATFORMS"

    docker buildx build $NO_CACHE \
        --platform "$PLATFORMS" \
        -t "$CLIENT_IMAGE" \
        -f client/Dockerfile \
        --target production \
        --build-arg "VITE_BIFROST_VERSION=${BIFROST_VERSION}" \
        $BUILD_OUTPUT \
        ./client

    echo -e "${GREEN}Client image built successfully${NC}"
    echo ""
fi

echo ""
echo -e "${GREEN}Build complete!${NC}"

if [ "$BUILD_API" = true ]; then
    echo "  API:    $REGISTRY/bifrost-api:$TAG"
fi
if [ "$BUILD_CLIENT" = true ]; then
    echo "  Client: $REGISTRY/bifrost-client:$TAG"
fi

if [ "$PUSH" = true ]; then
    echo ""
    echo "Images pushed to registry with platforms: $PLATFORMS"
else
    echo ""
    echo "To build and push multi-arch images, run: $0 -t $TAG -p"
fi
