FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    iproute2 \
    iputils-ping \
    net-tools \
    tcpdump \
    iperf3 \
    iw \
    wireless-tools \
    tshark \
    curl \
    python3 \
    python3-pip \
    python3-cryptography \
    openssl \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/drone-sec

# Contexto de build deve ser SIOT_topologies/
# (o Makefile já garante isso).
COPY scripts/ /opt/drone-sec/bin/

RUN chmod +x /opt/drone-sec/bin/*.py \
 && ln -s /opt/drone-sec/bin/group_auth.py      /opt/drone-sec/bin/group-auth \
 && ln -s /opt/drone-sec/bin/traffic_agent.py   /opt/drone-sec/bin/traffic-agent \
 && ln -s /opt/drone-sec/bin/metrics_agent.py   /opt/drone-sec/bin/metrics-agent \
 && ln -s /opt/drone-sec/bin/malicious_agent.py /opt/drone-sec/bin/malicious-agent

CMD ["/bin/bash"]
