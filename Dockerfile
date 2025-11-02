# 使用 Ubuntu 20.04 作为基础镜像（腾讯云镜像）
FROM ccr.ccs.tencentyun.com/library/ubuntu:20.04

# 设置非交互式安装
ENV DEBIAN_FRONTEND=noninteractive

# 配置国内镜像源
RUN sed -i 's/archive.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list && \
    sed -i 's/security.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    gcc-9 \
    g++-9 \
    gdb \
    valgrind \
    cmake \
    make \
    git \
    wget \
    curl \
    vim \
    nano \
    build-essential \
    pkg-config \
    libgtk-3-dev \
    libsqlite3-dev \
    libeigen3-dev \
    libgsl-dev \
    libxml2-dev \
    libxml2-utils \
    libxml2 \
    libboost-all-dev \
    libssl-dev \
    libffi-dev \
    bc \
    && rm -rf /var/lib/apt/lists/*

# 设置 gcc-9 为默认编译器
RUN update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-9 90 \
    && update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-9 90

# 安装 Python 依赖
RUN pip3 install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple/
RUN pip3 install -i https://pypi.tuna.tsinghua.edu.cn/simple/ \
    networkx \
    numpy \
    matplotlib \
    scipy \
    pandas \
    seaborn \
    jupyter \
    ipython \
    fastapi \
    uvicorn

# 设置工作目录
WORKDIR /workspace

# 复制项目文件
COPY . /workspace/

# 配置 NS-3（不构建，在运行时构建）
RUN ./ns3 configure --enable-examples --enable-tests

# 设置环境变量
ENV NS3_HOME=/workspace
ENV PATH=$NS3_HOME:$PATH

# 创建结果目录
RUN mkdir -p /workspace/results

# 暴露端口（如果需要 Jupyter）
EXPOSE 8888

# 默认命令
CMD ["/bin/bash"]
