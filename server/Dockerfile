# ── Stage 1 : build 3gxtool + devkitARM ──────────────────────────────────────
FROM devkitpro/devkitarm AS builder

ARG THREEGXTOOL_REPO=https://gitlab.com/thepixellizeross/3gxtool
ARG THREEGXTOOL_REF=master

WORKDIR /opt
RUN git clone --recursive --depth 1 --branch ${THREEGXTOOL_REF} ${THREEGXTOOL_REPO} 3gxtool \
    && cmake -S /opt/3gxtool -B /opt/3gxtool/build-linux \
             -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    && cmake --build /opt/3gxtool/build-linux -j \
    && install -m 0755 /opt/3gxtool/build-linux/3gxtool /usr/local/bin/3gxtool

# ── Stage 2 : image finale (Python server + outils de build) ─────────────────
FROM devkitpro/devkitarm

# Copier 3gxtool depuis le stage 1
COPY --from=builder /usr/local/bin/3gxtool /usr/local/bin/3gxtool

# Python 3 + pip
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dépendances Python
COPY requirements.txt ./
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# Sources du serveur + fichiers de build plugin
COPY main.py tid_map.json ./
COPY Sources/   Sources/
COPY Includes/  Includes/
COPY Makefile   3ds.ld discord-rpc.plgInfo ./

ENV THREEGXTOOL=/usr/local/bin/3gxtool \
    DRPC_UDP_HOST=0.0.0.0 \
    DRPC_UDP_PORT=5005 \
    DRPC_WS_HOST=0.0.0.0 \
    DRPC_WS_PORT=8765 \
    DRPC_HTTP_HOST=0.0.0.0 \
    DRPC_HTTP_PORT=8766

EXPOSE 5005/udp 8765 8766

# Le serveur build le plugin en lançant make directement (pas docker-in-docker)
CMD ["python3", "main.py"]

