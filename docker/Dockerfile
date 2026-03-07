FROM devkitpro/devkitarm

ARG THREEGXTOOL_REPO=https://gitlab.com/thepixellizeross/3gxtool
ARG THREEGXTOOL_REF=master

WORKDIR /opt

# Build a Linux-native 3gxtool used by Makefile packaging step.
RUN git clone --recursive --depth 1 --branch ${THREEGXTOOL_REF} ${THREEGXTOOL_REPO} 3gxtool \
    && cmake -S /opt/3gxtool -B /opt/3gxtool/build-linux -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    && cmake --build /opt/3gxtool/build-linux -j \
    && install -m 0755 /opt/3gxtool/build-linux/3gxtool /usr/local/bin/3gxtool

WORKDIR /work
ENV THREEGXTOOL=/usr/local/bin/3gxtool

CMD ["bash", "-lc", "make clean all THREEGXTOOL=/usr/local/bin/3gxtool"]
