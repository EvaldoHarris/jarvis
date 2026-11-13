FROM debian:bookworm-slim
RUN dpkg --add-architecture i386 && apt-get update && apt-get install -y --no-install-recommends wine wine32:i386 wine64 python3 ffmpeg xvfb xauth && rm -rf /var/lib/apt/lists/*
COPY python/ /opt/python/
COPY sdk/ /opt/sdk/
COPY worker.py entry.py stream.py /opt/probe/
ENV HOME=/work WINEPREFIX=/work/wine WINEARCH=win32 WINEDEBUG=-all PYTHONDONTWRITEBYTECODE=1
USER 1000:1000
WORKDIR /work
ENTRYPOINT ["python3", "/opt/probe/entry.py"]
