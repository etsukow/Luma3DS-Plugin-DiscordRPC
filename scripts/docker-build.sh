#!/usr/bin/env sh
set -eu

IMAGE_NAME="${IMAGE_NAME:-luma-drpc-builder}"
DOCKERFILE_PATH="${DOCKERFILE_PATH:-docker/Dockerfile}"
THREEGXTOOL_REPO="${THREEGXTOOL_REPO:-https://gitlab.com/thepixellizeross/3gxtool}"
THREEGXTOOL_REF="${THREEGXTOOL_REF:-master}"
TARGET="${1:-all}"

if [ ! -f "$DOCKERFILE_PATH" ]; then
    echo "Missing Dockerfile: $DOCKERFILE_PATH" >&2
    exit 1
fi

if [ ! -f "Makefile" ]; then
    echo "Run this script from the project root (Makefile not found)." >&2
    exit 1
fi

docker build \
    -f "$DOCKERFILE_PATH" \
    --build-arg THREEGXTOOL_REPO="$THREEGXTOOL_REPO" \
    --build-arg THREEGXTOOL_REF="$THREEGXTOOL_REF" \
    -t "$IMAGE_NAME" .

if [ -f ".env" ]; then
    docker run --rm \
        --env-file .env \
        -v "$PWD":/work \
        -w /work \
        "$IMAGE_NAME" \
        sh -lc "make clean $TARGET THREEGXTOOL=/usr/local/bin/3gxtool"
else
    docker run --rm \
        -v "$PWD":/work \
        -w /work \
        "$IMAGE_NAME" \
        sh -lc "make clean $TARGET THREEGXTOOL=/usr/local/bin/3gxtool"
fi
