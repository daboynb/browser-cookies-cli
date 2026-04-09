FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        wget gnupg ca-certificates \
        dbus dbus-x11 gnome-keyring libsecret-1-0 \
        firefox-esr procps xvfb xdotool \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub \
        | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
        > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

RUN dbus-uuidgen > /etc/machine-id

RUN pip install --no-cache-dir cryptography secretstorage selenium

COPY . /src/browser_cookies_cli
WORKDIR /src
ENV PYTHONPATH=/src
RUN chmod +x browser_cookies_cli/tests/run.sh

ENTRYPOINT ["browser_cookies_cli/tests/run.sh"]
