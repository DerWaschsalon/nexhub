FROM python:3.12-slim

# ffmpeg: Audio umwandeln, libopus: Sprachkanal, deno: braucht yt-dlp für YouTube,
# fonts-dejavu-core: Schrift für die Rangkarte (Levelsystem)
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg libopus0 ca-certificates fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot ./bot
COPY entrypoint.sh .

# Stand des Codes (z. B. "main@71b65a2"), zeigt der Hub unter Bot → Übersicht
ARG GIT_REV=dev
ENV PYTHONUNBUFFERED=1 DB_PATH=/data/bot.sqlite3 GIT_REV=$GIT_REV
VOLUME /data
EXPOSE 8787
EXPOSE 8789
# Steuer-API für den NexHub, nur mit BOT_CONTROL_KEY und nur im internen Netz
EXPOSE 8790
ENTRYPOINT ["sh", "/app/entrypoint.sh"]
