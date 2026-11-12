# Карта консолидации демо

База: e73b31ab (#308). Каноническая пользовательская конфигурация: `examples/demo`. Корневой README не редактируется.

Phase 1 из 6749f5a уже включён: original demo собирается для исторических тестов из 18 канонических файлов и одного legacy root. Отдельная копия удалена.

## Оставшиеся зависимости
Числа ниже показывают текстовые зависимости от путей, не полноту покрытия. Перед удалением нужны функциональный перенос и проверка оставшихся динамических зависимостей.

### `examples/configuration-application-host`: 4 файлов
- `tests/test_configuration_application_example.py`
- `tests/test_application_host_browser_qa_contract.py`
- `tests/browser_ui/application_host_browser_qa.mjs`
- `docs/configuration-application-host.md`

### `examples/configuration-business-application`: 5 файлов
- `tests/test_sqlite_launch_snapshot.py`
- `tests/test_configuration_business_example.py`
- `tests/test_business_browser_qa_contract.py`
- `tests/browser_ui/business_browser_qa.mjs`
- `docs/configuration-business-application.md`

### `examples/configuration-catalog-forms`: 7 файлов
- `tests/test_sqlite_launch_snapshot.py`
- `tests/test_configuration_catalog_forms.py`
- `tests/test_configuration_browser_qa_contract.py`
- `tests/browser_ui/configuration_catalog_fixture.py`
- `tests/browser_ui/configuration_browser_qa.mjs`
- `tests/browser_ui/application_host_browser_qa.mjs`
- `docs/configuration-catalog-forms.md`

### `examples/configuration-dialogs`: 5 файлов
- `tests/test_configuration_dialogs_browser_qa_contract.py`
- `tests/test_configuration_dialogs.py`
- `tests/browser_ui/configuration_dialogs_browser_qa.mjs`
- `docs/configuration-value-input.md`
- `docs/configuration-dialogs.md`

### `examples/configuration-document-forms`: 8 файлов
- `tests/test_sqlite_launch_snapshot.py`
- `tests/test_document_form_browser_qa_contract.py`
- `tests/test_database_ui_launch_process.py`
- `tests/test_configuration_document_replication.py`
- `tests/test_configuration_document_app.py`
- `tests/browser_ui/document_form_fixture.py`
- `tests/browser_ui/document_form_browser_qa.mjs`
- `docs/configuration-document-forms.md`

### `examples/configuration-form-results`: 5 файлов
- `tests/test_configuration_results_browser_qa_contract.py`
- `tests/test_configuration_form_results.py`
- `tests/browser_ui/configuration_results_browser_qa.mjs`
- `docs/configuration-results-browser-qa.md`
- `docs/configuration-form-results.md`

### `examples/configuration-forms/counter`: 1 файлов
- `docs/configuration-forms.md`

### `examples/configuration-forms/layouts`: 4 файлов
- `tests/test_configuration_layout_browser_qa_contract.py`
- `tests/browser_ui/configuration_layout_browser_qa.mjs`
- `docs/configuration-layout-browser-qa.md`
- `docs/configuration-forms.md`

### `examples/configuration-forms/welcome`: 1 файлов
- `docs/configuration-forms.md`

### `examples/configuration-inventory-application`: 9 файлов
- `tests/test_inventory_statement_fixture_smoke.py`
- `tests/test_inventory_application_browser_qa_contract.py`
- `tests/inventory_application_fixture.py`
- `tests/browser_ui/object_form_preflight_browser_qa.mjs`
- `tests/browser_ui/inventory_statement_browser_qa.mjs`
- `tests/browser_ui/inventory_application_browser_qa.mjs`
- `docs/inventory-statement-browser-qa.md`
- `docs/inventory-application-browser-qa.md`
- `docs/configuration-inventory-application.md`

### `examples/configuration-posting-application`: 5 файлов
- `tests/test_sqlite_launch_snapshot.py`
- `tests/test_posting_application_browser_qa_contract.py`
- `tests/test_configuration_posting_app.py`
- `tests/browser_ui/posting_application_browser_qa.mjs`
- `docs/configuration-posting-application.md`

### `examples/configuration-reference-application`: 6 файлов
- `tests/test_sqlite_launch_snapshot.py`
- `tests/test_configuration_reference_profile.py`
- `tests/test_configuration_reference_browser_qa_contract.py`
- `tests/browser_ui/configuration_reference_browser_qa.mjs`
- `docs/configuration-reference-browser-qa.md`
- `docs/configuration-reference-application.md`

### `examples/configuration-scalar-editors`: 5 файлов
- `tests/test_scalar_editor_browser_qa_contract.py`
- `tests/test_configuration_scalar_editors.py`
- `tests/browser_ui/scalar_editor_browser_qa.mjs`
- `docs/typed-scalar-browser-qa.md`
- `docs/typed-form-scalar-editors.md`

### `examples/configuration-value-input`: 4 файлов
- `tests/test_configuration_value_input_example.py`
- `tests/test_configuration_value_input_browser_qa_contract.py`
- `tests/browser_ui/configuration_value_input_browser_qa.mjs`
- `docs/configuration-value-input.md`

### `examples/forms/order-intake/configuration`: 7 файлов
- `tests/test_orders_workspace.py`
- `tests/test_order_workbench.py`
- `tests/test_form_browser_qa_contract.py`
- `tests/browser_ui/form_browser_qa.mjs`
- `docs/orders-workspace.md`
- `docs/order-workbench.md`
- `docs/form-tables.md`

### `examples/forms/product-intake/configuration`: 3 файлов
- `tests/test_form_browser_qa_contract.py`
- `tests/browser_ui/form_browser_qa.mjs`
- `docs/form-app.md`

### `examples/forms/reference-order/configuration`: 3 файлов
- `tests/test_reference_browser_qa_contract.py`
- `tests/browser_ui/reference_browser_qa.mjs`
- `docs/reference-orders.md`

## Следующий крупный блок
- Inventory + inventory-enum: переносить в main demo полноценные сценарии документов, проведения и отчётов. Добавлены 3 теста canonical source: исключение несохранённых/непроведённых документов из движений; отмена проведения/повторное проведение/переоткрытие с enum; пометка исторической ссылки без потери движений.
- Старые exact-profile admission/negative и native-acquisition pins не выдавать за приёмку новой конфигурации. Минимальные источники оставлять только после выделения действительно необходимого контракта; не перемещать все директории целиком в fixtures.
- Forms/dialogs/results/value-input: основная демо уже имеет OperationDraft/DraftDetails; перенести общие UX сценарии, сохранить минимальные отрицательные parser fixtures отдельно.
- Scalar editors и information-register posting: сначала включить соответствующую существенную функциональность в основную конфигурацию. Не маскировать различия простой заменой путей.

## Merge blocker
`README.md:59` указывает на удалённый `tests/fixtures/demo_cf/source`. Пользователь редактирует README; требуется его явное решение, файл здесь не менялся.

Нативные XML/BSL и source hashes #308 этим блоком не меняются. Нынешние 3 host-теста не являются browser/native проверкой и пока не разрешают удаление всех 19 старых конфигураций.

## Реальный перенос inventory-правила

В основной `Documents/Issue/Ext/ObjectModule.bsl` перенесён запрет отрицательного остатка из non-enum inventory. Enum-поля и прежние диагностические Mode 1/2 сохранены. Это новые исходные байты, поэтому прежний native результат к ним не относится; требуется свежий Designer load/check. Проверяется атомарный отказ и успешный повтор после исправления количества.

## Удалённая копия enum-конфигурации

`examples/configuration-inventory-enum-application` удалена: все 23 файла точно
воспроизводились уже существующим генератором `tests/inventory_enum_application_fixture.py`.
Новые копии в fixtures не создавались. Точный historical digest закреплён тестом;
browser acquisition собирает ту же историческую базу генератором и связывает
результат с обоими генераторами, non-enum forms и enum runtime source.
Основная демо остаётся `examples/demo`; количество пользовательских XML-конфигураций
снижено с 20 до 19. Остальные удаляются по мере фактического переноса сценариев.

## Перенос CLI-склада на основную демо

Шесть BSL-сценариев `examples/inventory_reference/*.bsl` используют одну конфигурацию
`examples/demo`: исходные русские справочники, обязательный вид номенклатуры и строки
складов, Receipt/Issue и Stock. Отдельная `examples/inventory_reference/source`
(8 файлов) удалена, число конфигураций теперь 18. Проверяется реальное исполнение
CLI в разных процессах, reopen, отказ расхода, перепроведение и периодные отчёты.
Historical native12 replay по-прежнему читает неизменные measured runtime sources.
