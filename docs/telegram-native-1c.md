# Telegram: запрос ручного прогона на реальной 1С

Workflow `.github/workflows/notify-native-1c.yml` отправляет владельцу личное
сообщение только при **добавлении** метки `needs-native-1c-run` к открытому PR
в `Atridis/yadinassi`, направленному в `main`. Метку ставит сопровождающий,
только когда явно нужен отдельный ручной прогон версии или платформы, не
покрытой [автоматическим PR/main CI](native-1c-ci.md). Для поддерживаемого
Docker CI эта метка и ручной прогон не нужны. Сам статус draft,
новые коммиты и падение CI сообщений не вызывают. Draft PR с этой меткой
уведомляет: именно в нём могут быть подготовлены новые тесты для владельца.

Пример сообщения:

> Для PR #42 нужен ручной прогон на реальной 1С.
> https://github.com/Atridis/yadinassi/pull/42
> Пожалуйста, запустите интеграционные тесты из этого PR и обновите результаты
> в integrational_tests/output и сведения о прогоне в integrational_tests/meta.md.

Текст не содержит заголовка, описания, комментариев, кода PR или результатов
тестов. Telegram получает номер и ссылку на PR, стандартную просьбу и ID
настроенного личного чата. Предпросмотр ссылки отключён.

## Настройка владельцем

1. Откройте официального [@BotFather](https://t.me/BotFather) в Telegram.
   Создайте своего бота командой `/newbot` по
   [официальной инструкции](https://core.telegram.org/bots/tutorial#obtain-your-bot-token).
   Полученный токен храните как пароль. Не присылайте его в PR, issue, чат
   с помощником или сторонним ботам.
2. Откройте **личный** диалог со своим ботом и нажмите Start
   (или отправьте `/start`). Бот не может начать такой диалог первым.
3. Определите ID именно этого диалога через официальный
   [getUpdates](https://core.telegram.org/bots/api#getupdates).
   Используйте локальный доверенный клиент; токен не вставляйте в адресную
   строку браузера, аргументы командной строки или историю shell.
   Например, следующий Python-код запросит токен скрытым вводом и выведет
   только числовые ID личных чатов с именами пользователей. Сверьте свой
   username; если в списке несколько пользователей, не выбирайте наугад.
   При пустом результате ещё раз отправьте своему боту `/start`.
   Для бота с уже настроенным webhook используйте отдельного нового бота:
   `getUpdates` и webhook одновременно не работают.

   ```python
   import getpass
   import json
   import urllib.request

   token = getpass.getpass("Bot token (hidden): ")
   try:
       # Run locally without HTTP debug logging; do not share the response.
       request = urllib.request.Request(
           "https://api.telegram.org/bot" + token + "/getUpdates",
           data=b'{"timeout": 0}',
           headers={"Content-Type": "application/json"},
       )
       with urllib.request.urlopen(request, timeout=15) as response:
           updates = json.load(response)
       for update in updates.get("result", []):
           chat = update.get("message", {}).get("chat", {})
           if chat.get("type") == "private":
               print(chat["id"], chat.get("username", "(no username)"))
   except Exception:
       print("Could not read updates. Check the token and your private chat.")
   finally:
       token = None
   ```

4. В репозитории откройте **Settings → Secrets and variables → Actions →
   New repository secret** и самостоятельно сохраните:
   - `TELEGRAM_BOT_TOKEN` — токен своего бота;
   - `TELEGRAM_CHAT_ID` — положительный числовой ID своего личного чата.
   Группы, каналы, username и отрицательные ID намеренно не поддерживаются.
   Не добавляйте значения в код или Actions variables. Подробнее:
   [GitHub Actions secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).
5. После слияния этого workflow в `main` создайте в репозитории метку
   `needs-native-1c-run`, если её ещё нет. Добавляйте её только к PR,
   для которого нужен ручной прогон. Для проверки настройки используйте
   настоящий такой запрос: добавление метки отправляет реальное сообщение.
   Наличие метки до установки workflow само по себе ничего не отправит.

## Повторный запрос и ошибки

После получения результатов снимите метку. Если появились новые тесты,
которые требуют другого прогона, снова добавьте её. Обычный push с уже
установленной меткой не посылает сообщение.

Повторный запуск того же Actions run пропускается, чтобы не дублировать
сообщение. Для повторной попытки после исправления настройки снимите и снова
добавьте метку. При тайм-ауте сначала проверьте Telegram: сообщение могло
дойти. Автоматических сетевых повторов нет. Это не гарантия exactly-once
доставки: новое добавление метки создаёт отдельный запрос.

Если секреты не настроены или формат неверен, job завершается с явной
ошибкой конфигурации, без сетевого запроса и без печати значений. При ошибке
Telegram или сети job завершается с обезличенной ошибкой. Успех означает,
что Telegram API принял запрос, а не что владелец прочитал сообщение.
Не делайте этот вспомогательный job обязательной проверкой для слияния:
он не заменяет CI, ревью или нативные эталоны. Настройки защиты веток этот
workflow не меняет.

## Граница доверия

Используется [pull_request_target](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request_target)
с единственным событием `labeled`. Checkout закреплён на SHA действия и
берёт только скрипт **из SHA базовой ветки**, никогда из PR head/merge ref.
В привилегированном job нет установки зависимостей, выполнения тестов PR,
загрузки артефактов PR или кеша. Скрипт запускается в изолированном режиме
Python. Права GitHub token ограничены `contents: read`, сохранение
credentials отключено; секреты передаются только шагу отправки.

Это позволяет обслуживать PR из fork, не выполняя их код с секретами.
Люди с правом назначать метки могут инициировать уведомление: выдавайте
это право только доверенным сопровождающим. Base-ветка `main` должна
оставаться доверенной. При отправке используется только фиксированный
HTTPS endpoint Telegram, без переходов по HTTP redirect; поля PR не
подставляются в команды. Токен, URL API и ответ Telegram не печатаются.

Офлайн-проверки входят в обычный `python -m unittest discover -s tests -v`.
Отдельно: `python -m unittest discover -s tests -p test_native_notification.py -v`.
Они подменяют сеть, не требуют секретов и не отправляют Telegram-сообщения.
