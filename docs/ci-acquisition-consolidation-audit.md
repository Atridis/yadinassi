# M9: измеренная карта перед объединением acquisition

Это план следующей безопасной миграции, не реализованная экономия и не
разрешение убрать проверки. База измерения: успешный полный run43580003908,
source53fdd9f0a0b25f7a635bf1f8c07b2ce94aee3cfc, head31196788/base da445.
Семь partition ZIP проверены по опубликованным SHA256, размеру, CRC и binding.

## Подтверждённый повтор historical execution

| Тест | Linux, с | Windows, с | mac-x86, с |
| --- | ---: | ---: | ---: |
| NativeMoveTests.test_all_prior1021_messages_unchanged_on_both_targets | 36.808 | 30.375 | 142.930 |
| NativeTotalTests.test_complete_old1022_messages_unchanged_on_both_targets | 38.361 | 31.249 | 138.705 |

Оба выполняют длинный historical script на двух targets с настоящим и
искусственно отсутствующим методом. Но их source hashes/prefix lengths и
native32 suffix различаются. Нельзя считать два исполнения текущего движка
независимым историческим oracle. Existing `ci-audit-coverage-plan.md` уже
помечает этот C2 как blocked. Ни тесты, ни независимые native32 fixtures не
удалены. Для сокращения сначала нужен проверенный oracle для каждого точного
prefix и карта неизменённых assertions; новый fixture нельзя генерировать из
текущего implementation output.

## Frozen smoke

C1 уже убрал 60 повторных success-route launches согласно
`ci-smoke-launch-inventory.md`. Например TextDocument теперь сохраняет BOM-file
и incremental console, а shared transports принадлежат отдельной матрице.
Убрать их ещё раз как «дубли» нельзя. Saved native outputs, пакетированные
ресурсы/зависимости, timezone, UI lifecycle и отрицательные пути остаются
независимыми. В этом исследовании новый безопасно удаляемый запуск не доказан.

## Закрытая общая acquisition-обвязка

В repository25 native-1c workflow файлов; не все имеют одинаковый протокол.
Первый потенциальный пилот: common templates / session parameters / temporary
storage, а не одновременная миграция всех host drivers.

Безопасный reusable workflow должен принимать только enum profile, без
произвольных script paths, shell arguments, image tags, artifact globs или ref.
Закрытая таблица профилей фиксирует caller branch, host script, timeout,
summary/observation paths и output-ready flag. Неизвестное значение отказывает
до checkout/credentials. Profile branch gate сохраняется и в caller, и в
общем admission; событие, repository/owner numeric IDs, actor/triggering actor,
base/head/synthetic merge parents остаются обязательными.

Checkout остаётся exact github.sha, persist-credentials=false, submodules/lfs
false. До GHCR credentials выполняется существующий source-bound bind.
Pinned Python/dependencies/action SHAs, approved image digest, read-only isolated
container/network policy, owned cleanup/census и nonce checks не меняются.
Credentials не передаются через profile input и не попадают в outputs.
Concurrency/непересечение owned ресурсов сохраняются отдельно по profile/PR.

Общая обвязка не заменяет независимые profile fixtures, observer source pins,
исторические native observations или индивидуальные finite output validators.
Summary загружается always, observations только при проверенном ready flag,
в фиксированных bounded paths. Нельзя использовать success общего wrapper как
native acceptance каждого профиля.

Перед миграцией нужны negative tests unknown/profile-branch mismatch,
foreign actor/repository/base/head/source, missing ready marker и output drift;
затем один source-bound acquisition пилота с проверкой artifact provenance.
Исторические golden bytes не переписываются ради новой структуры workflow.
UI M5 JavaScript job checkpoint ccfb3d8f остаётся отдельным и должен быть сохранён
при будущей интеграции. Этот документ workflow не меняет и CI не запускает.
