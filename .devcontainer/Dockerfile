# Dev Container for meter_buddy
FROM mcr.microsoft.com/devcontainers/base:ubuntu-22.04

# Arguments
ARG NODE_VERSION=20

# Install common packages, Node.js, Python, PlatformIO and udev for device access
RUN apt-get update \
 && apt-get -y install --no-install-recommends curl ca-certificates build-essential git udev \
 && curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
 && apt-get -y install nodejs python3 python3-pip python3-venv python3-serial \
 && pip3 install --no-cache-dir --upgrade pip platformio \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set working directory inside container
WORKDIR /workspaces/meter_buddy

# Ensure a non-root user is used (base image provides 'vscode')
USER vscode
