# XML-соответствия существующих типов

`XMLТип` / `XMLType`, `XMLТипЗнч` / `XMLTypeOf` и
`ИзXMLТипа` / `FromXMLType` связывают существующие дескрипторы типов с
`ТипДанныхXML` / `XMLDataType`. Последний хранит неизменяемые
`ИмяТипа` / `TypeName` и `URIПространстваИмен` / `NamespaceURI`.
Конструктор принимает имя и URI как строки, не загружая внешние ресурсы.

Поддержанный локальный контракт основан на [официальном руководстве,
§15.2.3](https://1c-dn.com/download-trial/files/guides/developer_guide.pdf):

- String, Boolean, Number, Date, BinaryData: `string`, `boolean`, `decimal`,
  `dateTime`, `base64Binary` в `http://www.w3.org/2001/XMLSchema`.
- UUID, Null, ValueStorage, Type, TypeDescription: одноимённые XML-типы
  в `http://v8.1c.ru/data`.
- Реальные типы CatalogRef/CatalogObject, DocumentRef/DocumentObject,
  EnumRef: английский префикс и имя объекта, пустой namespace.

Это **legacy XML**, не namespace реестра XDTO `http://v8.1c.ru/8.1/data/core`.
Соответствие типа не означает готовность XML-сериализатора его значений:
например, ValueStorage и объекты БД не получают новый XML codec этим блоком.

Обратный вызов принимает один XMLDataType либо две строки: имя и URI.
Регистр и namespace значимы. Для метаданных возвращается только дескриптор
существующего объекта текущего контекста; неизвестное имя даёт Undefined.
Никакие объекты БД, менеджеры, ссылки или идентичности не создаются.
Ошибки закрытого контекста и неподдержанной source-декларации не скрываются.

Ограничения: остальные платформенные семейства не отображаются автоматически.
Для них XMLType/XMLTypeOf выдаёт явную ошибку неподдержанного соответствия,
а не обещает стандартный fallback Undefined для всей платформы. Пределы
длины имени/URI 1024/4096 являются бюджетами реализации. Native parity
нового bridge не измерялась; это документированный локальный срез.

Тесты: `test_xml_type_bridge.py`, существующие XML lexical conversion,
type identity, metadata descriptor и source-enumeration наборы.
