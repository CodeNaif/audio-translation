ARG BASE_IMAGE=vllm/vllm-openai:latest
FROM ${BASE_IMAGE}

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir "vllm[audio]"
