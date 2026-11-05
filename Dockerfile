FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN sed -i 's|http://archive.ubuntu.com/ubuntu|http://mirrors.aliyun.com/ubuntu|g; s|http://security.ubuntu.com/ubuntu|http://mirrors.aliyun.com/ubuntu|g' /etc/apt/sources.list.d/ubuntu.sources \
    && apt-get update -o Acquire::Retries=3 \
    && apt-get install -y --no-install-recommends \
       build-essential cmake ninja-build pkg-config python3 python3-pip \
       python3-venv libboost-dev libgsl-dev libxml2-dev libsqlite3-dev \
       ca-certificates nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
COPY requirements-container.txt /tmp/requirements-container.txt
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    -r /tmp/requirements-container.txt

RUN useradd --create-home --uid 1001 sim \
    && mkdir -p /workspace/build /workspace/cmake-cache /workspace/examples/Reverie/dump \
    && chown -R sim:sim /workspace
WORKDIR /workspace
COPY --chown=sim:sim . /workspace/
# Git on Windows may check out executable scripts with CRLF or without +x.
RUN python3 -c "from pathlib import Path; files = [Path('ns3'), *Path('.').rglob('*.sh')]; [(p.write_bytes(p.read_bytes().replace(b'\r\n', b'\n')), p.chmod(0o755)) for p in files]"
USER sim
ENV USER=sim NS3_HOME=/workspace PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLBACKEND=Agg
EXPOSE 8000
CMD ["bash", "scripts/start-api.sh"]
