# Build only: users do not need Docker. The exported filesystem also serves as
# the private WSL distribution. Installed package versions are recorded below.
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git python3 perl make g++ binutils tcl klayout \
    libegl1 libopengl0 time procps magic ngspice python3-venv \
    build-essential pkg-config tcl-dev tk-dev libx11-dev libxext-dev \
    libxrender-dev libxpm-dev libcairo2-dev libreadline-dev zlib1g-dev m4 csh bison flex \
    && rm -rf /var/lib/apt/lists/*
COPY build_physical_engines.py /tmp/physical-build/scripts/build_physical_engines.py
COPY examples/physical-engine-lock.json /tmp/physical-build/examples/physical-engine-lock.json
RUN python3 /tmp/physical-build/scripts/build_physical_engines.py --output /opt/icstudio/physical --jobs 2 \
    && python3 -m venv /opt/icstudio/python \
    && /opt/icstudio/python/bin/pip install --no-cache-dir klayout==0.30.5
RUN curl -fL --retry 3 -o /tmp/openroad.deb https://vaultlink.precisioninno.com/api/releases/26Q2-1164-g08f67ee5ec/openroad_26Q2-1164-g08f67ee5ec_amd64-ubuntu-24.04.deb/download \
    && echo 'f3f1eeaa18f327503f72cc45dcef5b1514ec2e89726ec53b4553bf4f951168a3  /tmp/openroad.deb' | sha256sum -c \
    && apt-get update && apt-get install -y /tmp/openroad.deb \
    && rm -rf /var/lib/apt/lists/* /tmp/openroad.deb
RUN mkdir -p /opt/icstudio && curl -fL --retry 3 -o /tmp/oss.tgz https://github.com/YosysHQ/oss-cad-suite-build/releases/download/2026-09-13/oss-cad-suite-linux-x64-20260913.tgz \
    && echo '3df702b34cb83ed7bc540c02fa26008b7cfa379b645f441f0de876a84873da6b  /tmp/oss.tgz' | sha256sum -c \
    && tar -xzf /tmp/oss.tgz -C /opt/icstudio && rm /tmp/oss.tgz
RUN git init /opt/icstudio/orfs && cd /opt/icstudio/orfs \
    && git remote add origin https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts.git \
    && git fetch --depth 1 origin eaba6576441bf7c1743ea56ecdb1904210ec02c2 \
    && git checkout FETCH_HEAD
RUN curl -fL --retry 3 -o /tmp/klayout.deb https://www.klayout.org/downloads/Ubuntu-24/klayout_0.30.5-1_amd64.deb \
    && echo '9f88fe45d1992fc9bd0ce986bbbe150ad198c6a59a86fc13343db822a5790e49  /tmp/klayout.deb' | sha256sum -c \
    && apt-get update && apt-get install -y /tmp/klayout.deb \
    && rm -rf /var/lib/apt/lists/* /tmp/klayout.deb
COPY icstudio /tmp/studio/icstudio
COPY ihp-pdk /tmp/ihp-pdk
COPY compile_ihp_osdi.py /tmp/compile_ihp_osdi.py
RUN curl -fL --retry 3 -o /tmp/openvaf.tgz https://fides.fe.uni-lj.si/openvaf/download/openvaf-reloaded-osdi_0.3-31-gf47d557-linux_x64.tar.gz \
    && echo '9bc343d52e00529ddba452b90358cdd14da14ec7437d75dec2dbd621eda54bc8  /tmp/openvaf.tgz' | sha256sum -c \
    && mkdir /tmp/openvaf && tar -xzf /tmp/openvaf.tgz -C /tmp/openvaf \
    && PYTHONPATH=/tmp/studio python3 /tmp/compile_ihp_osdi.py --pdk-root /tmp/ihp-pdk --openvaf /tmp/openvaf/openvaf --output /opt/icstudio/osdi/ihp-sg13g2 --generic-cpu \
    && cp -r /tmp/ihp-pdk/libs.tech/verilog-a /opt/icstudio/osdi/ihp-sg13g2/sources \
    && rm -rf /tmp/openvaf /tmp/openvaf.tgz /tmp/ihp-pdk /tmp/compile_ihp_osdi.py
COPY licenses /opt/icstudio/licenses
COPY scripts /tmp/studio/scripts
COPY examples/sky130-reference-assets.json /tmp/studio/examples/sky130-reference-assets.json
COPY licenses/Apache-2.0.txt /tmp/studio/licenses/Apache-2.0.txt
COPY assemble.py bundle_platforms.py /tmp/
RUN python3 -m venv /tmp/platform-builder \
    && /tmp/platform-builder/bin/pip install --no-cache-dir backports.zstd==1.7.0 \
    && PYTHONPATH=/tmp/studio /tmp/platform-builder/bin/python /tmp/assemble.py \
    && rm -rf /tmp/platform-builder /tmp/studio /tmp/assemble.py /tmp/bundle_platforms.py
RUN printf '[automount]\noptions = "metadata"\n[interop]\nappendWindowsPath = false\n' > /etc/wsl.conf
CMD ["/bin/bash"]
