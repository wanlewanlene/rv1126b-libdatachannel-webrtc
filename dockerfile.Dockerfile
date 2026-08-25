FROM ubuntu:20.04

RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    wget \
    python3

# 安装交叉编译工具链
RUN wget https://repo.rock-chips.com/rv1106/toolchain/arm-rockchip830-linux-uclibcgnueabihf.tar.xz && \
    tar -xvf arm-rockchip830-linux-uclibcgnueabihf.tar.xz -C /opt && \
    rm arm-rockchip830-linux-uclibcgnueabihf.tar.xz

ENV PATH="/opt/arm-rockchip830-linux-uclibcgnueabihf/bin:${PATH}"
ENV CC=arm-rockchip830-linux-uclibcgnueabihf-gcc
ENV CXX=arm-rockchip830-linux-uclibcgnueabihf-g++

WORKDIR /app