# syntax=docker/dockerfile:1.7

FROM ubuntu:22.04

ARG DEBIAN_FRONTEND=noninteractive

# Русская локаль
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    locales \
    ca-certificates \
    && locale-gen ru_RU.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=ru_RU.UTF-8
ENV LC_ALL=ru_RU.UTF-8

# XFCE, TigerVNC и базовые библиотеки для 1С
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    xfce4 \
    xfce4-terminal \
    tigervnc-standalone-server \
    tigervnc-common \
    dbus-x11 \
    xauth \
    x11-utils \
    fonts-dejavu-core \
    fonts-liberation \
    libgtk2.0-0 \
    libgtk-3-0 \
    libnss3 \
    libxss1 \
    libasound2 \
    libwebkit2gtk-4.0-37 \
    policykit-1 \
    zenity \
    evince \
    libglu1-mesa \
    && rm -rf /var/lib/apt/lists/*

# Компоненты установщика 1С
ARG ONEC_VERSION=8.3.27.1508
ARG ONEC_COMPONENTS=client_full,desktop_icons,ru

# Устанавливаем только full-установщик заданной версии 1С.
# .run монтируется на время сборки, а не сохраняется в финальном слое.
RUN --mount=type=bind,source=installers,target=/mnt/installers,readonly \
    set -eux; \
    installer="/mnt/installers/setup-training-${ONEC_VERSION}-x86_64.run"; \
    test -f "$installer"; \
    cp "$installer" /tmp/1c-installer.run; \
    chmod +x /tmp/1c-installer.run; \
    timeout 600 /tmp/1c-installer.run \
        --mode unattended \
        --unattendedmodeui none \
        --installer-language ru \
        --enable-components "$ONEC_COMPONENTS"; \
    rm -f /tmp/1c-installer.run; \
    test -x "/opt/1cv8t/x86_64/${ONEC_VERSION}/1cv8t"; \
    test -x "/opt/1cv8t/x86_64/${ONEC_VERSION}/1cv8ct"

# Добавляем реальные исполняемые файлы 1С в PATH.
# 1cv8s может отсутствовать при клиентской установке: не подменяем его другой командой.
RUN set -eux; \
    for exe in 1cv8t 1cv8ct 1cv8st; do \
        target="/opt/1cv8t/x86_64/${ONEC_VERSION}/${exe}"; \
        if [ -x "$target" ]; then \
            ln -s "$target" "/usr/local/bin/$exe"; \
        else \
            echo "INFO: ${exe} not found in full client installation"; \
        fi; \
    done

# Утилиты TigerVNC для Ubuntu 22.04
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    tigervnc-tools \
    && rm -rf /var/lib/apt/lists/*

# Пользователь для графической сессии
RUN useradd -m -s /bin/bash onec \
    && mkdir -p /tmp/.X11-unix \
    && chmod 1777 /tmp/.X11-unix

# Скрипт запуска
COPY entrypoint.sh /usr/local/bin/entrypoint.sh

# Исправление Windows CRLF
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh \
    && sed -i '/./,$!d' /usr/local/bin/entrypoint.sh \
    && sed -i '1s/^\xEF\xBB\xBF//' /usr/local/bin/entrypoint.sh \
    && chmod +x /usr/local/bin/entrypoint.sh

USER onec

ENV HOME=/home/onec
ENV DISPLAY=:1

WORKDIR /home/onec

EXPOSE 5901

ENTRYPOINT ["/bin/bash", "/usr/local/bin/entrypoint.sh"]
