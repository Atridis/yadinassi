"""Informational wording only. The CLI harness still checks error behavior."""
from tests.test_cli import CLITests


# Documented 1C wording, not a capture of the same CLI probe.
REFERENCE = 'Индекс находится за границами массива'
REFERENCE_URL = 'https://its.1c.ru/db/content/updinfo/src/workflow/2.1.38/index.htm'


def main():
    observations = list(CLITests().array_bounds_diagnostics())
    differences = sum(actual != REFERENCE for _, actual in observations)
    print('### Текст ошибки: чтение массива за границей\n')
    print(f'Проверено: {len(observations)}. Отличается формулировка: {differences}.')
    print(f'Фраза из [документации 1С]({REFERENCE_URL}): `{REFERENCE}`.\n')
    for mode, actual in observations:
        print(f'- {mode}: `{actual}`')


if __name__ == '__main__':
    main()
