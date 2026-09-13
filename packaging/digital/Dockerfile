# Build only: users do not need Docker. The exported filesystem also serves as
# the private WSL distribution. Installed package versions are recorded below.
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git python3 perl make g++ binutils tcl klayout \
    libegl1 libopengl0 time procps && rm -rf /var/lib/apt/lists/*
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
COPY icstudio /tmp/studio/icstudio
COPY assemble.py /tmp/assemble.py
RUN PYTHONPATH=/tmp/studio python3 /tmp/assemble.py && rm -rf /tmp/studio /tmp/assemble.py
RUN printf '[automount]\noptions = "metadata"\n[interop]\nappendWindowsPath = false\n' > /etc/wsl.conf
CMD ["/bin/bash"]
