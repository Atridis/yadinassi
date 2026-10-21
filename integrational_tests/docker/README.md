# Сборка образа

## 1. Иерархия файлов

```text
/
├── Dockerfile
├── .dockerignore
├── entrypoint.sh
├── README.md
└── installers/                                # создать локально; не коммитить
    └── setup-training-<version>-x86_64.run    # положить самостоятельно
```

## 2. Варка образа

Создать подкаталог `installers` и положить туда дистриб:

```text
<директория сборки>\installers\setup-training-<version>-x86_64.run
```

Идем в корень проекта:

```powershell
cd <директория сборки>
```

В Dockerfile меняем версию:

```dockerfile
ARG ONEC_VERSION=<version>
```

```powershell
docker build `
  --platform linux/amd64 `
  --progress=plain `
  -t onec-ubuntu22:<version> `
  .
```

Успешное завершение выглядит как `exporting to image`, `naming to ...` и `DONE`. Сборка использует кеш Docker, если слои не изменились.

Проверить образ:

```powershell
docker image ls onec-ubuntu22
```

## 3. Проверка установки 1С

```powershell
docker run --rm `
  --entrypoint /bin/bash `
  onec-ubuntu22:<version> `
  -lc 'ls -l /opt/1cv8t/x86_64/<version>/; for cmd in 1cv8t 1cv8ct 1cv8st; do command -v "$cmd" || true; done'
```

## 4. Запустить контейнер с XFCE/VNC

Если есть контейнер с прошлого прогона:

```powershell
docker stop onec-desktop
docker rm onec-desktop
```

Далее задай **отдельный пароль для VNC** и запусти:

```powershell
$env:VNC_PASSWORD = Read-Host 'VNC password'

docker run -d `
  --name onec-desktop `
  --platform linux/amd64 `
  -p 127.0.0.1:5901:5901 `
  -e VNC_PASSWORD `
  -e VNC_GEOMETRY=1600x900 `
  -v onec-home-<version>:/home/onec `
  --restart unless-stopped `
  onec-ubuntu22:<version>

Remove-Item Env:VNC_PASSWORD
```

Том `onec-home-<version>` сохраняет пользовательские файлы и настройки между пересозданиями контейнера.

Проверить состояние:

```powershell
docker ps -a
docker logs onec-desktop
```

Ожидаемые сообщения:

```text
Starting VNC server...
Starting XFCE...
Desktop ready on VNC port 5901
```

Далее подключаемся через VNC клиент и проверяем работоспособность

Если VNC показывает чёрный экран или рабочий стол не запускается:

```powershell
docker exec onec-desktop bash -lc 'cat ~/.vnc/server.log ~/.vnc/xfce.log'
```

После проверки:

```powershell
docker stop onec-desktop
docker start onec-desktop
```

## 5. Публикация в приватный GitHub Container Registry

Авторизоваться в GHCR (пароль — GitHub PAT classic):

```powershell
docker login ghcr.io -u <login>
```

Создать тег и отправить:

```powershell
docker tag onec-ubuntu22:<version> `
  ghcr.io/<repo>/onec-ubuntu22:<version>

docker push ghcr.io/<repo>/onec-ubuntu22:<version>
```

Успешная публикация завершается строкой с тегом и `digest: sha256:...`. Если в конце `denied`, убедись, что токен имеет `write:packages` и тебе доступны права записи в пакет. Слои, уже отправленные в GHCR, при повторном `docker push` могут использоваться повторно.

Проверить манифест:

```powershell
docker manifest inspect ghcr.io/<repo>/onec-ubuntu22:<version>
```

Скачивание на другом компьютере (после `docker login`, при наличии `read:packages`):

```powershell
docker pull ghcr.io/<repo>/onec-ubuntu22:<version>
```

Для запуска скачанного образа используй команду из раздела 4, заменив в ней локальное имя образа на `ghcr.io/<repo>/onec-ubuntu22:<version>`.
