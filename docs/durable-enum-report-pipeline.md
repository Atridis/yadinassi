# Долгоживущие enum-таблицы отчётов

Рабочий блок для exact inventory-enum-v1/physical16: результаты enum-запросов,
внешние таблицы и временные таблицы менеджера сохраняют **домен значений**, но
не descriptor завершённого Execute и не read lease. Это отдельный host-контракт;
исторические native captures остаются неизменными и не доказывают новые semantics.

На каждом Execute выпускается новый локальный descriptor после проверки текущих
canonical namespace, Type, family generation, контекста и backend. Полный пакет
использует один owned composite read view: включая холодные metadata caches,
внешние таблицы, planning и постоянные источники. Metadata caches заполняются
атомарно из этого view; несовпадающий существующий cache не перезаписывается.

Параметры и все входные колонки/строки проверяются независимо от WHERE/TOP,
пустоты или проекции. Внешняя таблица копируется один раз. INTO/DESTROY остаются
staged: публикация менеджера возможна только после успеха всего пакета и закрытия
view. Его Close не требует проверки актуальности содержащихся значений.

Предварительная проверка чужих scalar/list параметров выполняется до открытия
view. Проверка несовместимых типов CASE/ISNULL/UNION выполняется в свежем read-only
snapshot, но до source scan и публикации. Это намеренное отличие времени отказа
от старого direct-only пути; второй planning на устаревших metadata не выполняется.

NULL и типизированная пустая ссылка различны. Mixed-enum output, defaults/Add,
casts, сериализация, ValueStorage, client/server transfer/capture, enum ordering
и MIN/MAX остаются закрыты. Information-register sources не получают нового grant.
Выгрузка и присваивание существующей ячейке проверяют exact canonical owner без
point-read; следующий Execute заново доказывает свежесть в своей lease.

Статус этого checkpoint: реализация и host tests подготовлены; результаты
проверок фиксируются отдельно, документ не является заявлением о PASS.
