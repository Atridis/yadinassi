# Явный interpreter-aware dispatch: первый срез констант

`HostFunction` остаётся обычной оболочкой явно зарегистрированного Python callable.
Interpreter передаётся только **точному** внутреннему `InterpreterCall`: frozen
дескриптор содержит границы arity, явный authorizer и generator dispatch. Наличие
у произвольного объекта `.invoke`, `.owner` или похожих атрибутов не даёт ему
interpreter-aware полномочий. Subclass не получает этот special dispatch.

Первый срез охватывает только source `ConstantCall`, `ConstantSetCall` и
`ValueManagerCall`. Их фабрики возвращают дескрипторы явно. Остальные host API и
markers не мигрированы. Дескриптор не является BSL-типом, не попадает в transport,
ValueStorage или новые grants. Raw marker внутри вручную созданного HostFunction
больше не получает interpreter автоматически: для этого внутреннего сценария
нужна явная `.descriptor()`.

После получения receiver, но **до вычисления аргументов**, descriptor проверяет
owner/family/side/lifetime и arity. Существующая проверка procedure/function
`returns_value` сохраняется. Перед actual invoke authorizer выполняется снова:
вычисление аргумента могло закрыть базу или инвалидировать владельца. Отдельные
операции сохраняют собственные проверки и типизацию значений.

Constant Set и набор Write вызывают generator `write_values`, а ValueManager
сохраняет generator `invoke`. Таким образом, BeforeWrite/OnWrite, отмена, rollback
и внешняя транзакция не заменяются прямыми `store.set/set_many`. Синхронный
внутренний read/create invoke сохранён для совместимости существующих host-тестов;
он не является новым BSL-dispatch entrypoint.

В расширении DB есть более строгий `SourceConstantValueManager.authorize` с
`_ready/_closed` и initialization checks. При объединении веток должен сохраниться
именно он; базовый source вариант не заменяет эту политику.

Это рефакторинг закрытого host boundary с дополнительной проверкой до аргументов,
не расширение поддержки native платформы. Нативные fixtures не менялись.
