FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    iproute2 \
    iputils-ping \
    net-tools \
    tcpdump \
    iperf3 \
    curl \
    python3 \
    python3-pip \
    openssl \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/drone-sec

COPY SIOT_topologies/scripts/ /opt/drone-sec/bin/

RUN chmod +x /opt/drone-sec/bin/*

CMD ["/bin/bash"]
