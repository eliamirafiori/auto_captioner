# Use NVIDIA's official Ubuntu 22.04 runtime image
FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

# Avoid timezone prompts during apt installs
ENV DEBIAN_FRONTEND=noninteractive

# Install Python, FFmpeg, Git, and Fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    ffmpeg \
    fonts-liberation \
    fonts-dejavu \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install PyTorch for CUDA 11.8 (Supports GTX 980 Ti / sm_52)
RUN pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
    
# Install Gradio and the original OpenAI Whisper (replaces faster-whisper)
RUN pip3 install --no-cache-dir gradio openai-whisper

RUN pip3 uninstall -y triton

# Copy our app
COPY app.py .

EXPOSE 7860

ENTRYPOINT ["python3", "app.py"]