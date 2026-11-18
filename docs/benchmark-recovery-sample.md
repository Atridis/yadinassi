## Изолированный bare: предварительные реконструированные сценарии

Не production default и не точная копия исторических workloads.
Обычный bare включает компиляцию AST; готовый bare исключает её. Профиль отдельно от времени.
Коммит `8a6b8edfce4b70b6c40093746d67fd1cebc322d2`; статусы: {'unbound': 268, 'measured': 144, 'skipped': 4}.
Python = 1×. Короткая серия, общая машина: не гарантия ускорения.

### N=512
| Сценарий | Python мс | Классы × | Bare с компиляцией × | Готовый bare × | Python/C готового bare |
|---|---:|---:|---:|---:|---:|
| method.map.get | 0.0237 | 1.20 | 14.82 | 1.30 | 5/516 |
| method.map.set | 0.0127 | 1.24 | 21.26 | 1.37 | 5/4 |
| method.map.iterate | 0.0228 | 0.99 | 12.96 | 1.55 | 5/4 |
| method.valuetable.get | 0.0192 | 3.79 | 18.09 | 3.68 | 1029/4 |
| method.valuetable.get_positional | 0.0200 | 2.33 | 22.44 | 2.32 | 517/4 |
| method.valuetable.iterate | 0.0151 | 3.41 | 24.77 | 3.69 | 518/4 |
| method.valuelist.get | 0.0210 | 2.94 | 15.75 | 2.93 | 517/516 |
| method.valuelist.iterate | 0.0162 | 2.90 | 20.66 | 3.19 | 517/3 |
| method.array.get | 0.0161 | 1.98 | 16.46 | 2.09 | 517/4 |
| method.array.set | 0.0074 | 3.43 | 37.69 | 3.72 | 517/4 |
| method.array.iterate | 0.0112 | 1.00 | 21.07 | 1.40 | 6/4 |
| method.map.insert | 0.0127 | 3.00 | 22.92 | 3.18 | 5/4 |
| assignment | 0.0068 | 1.02 | 25.18 | 1.18 | 5/3 |
| addition | 0.0127 | 1.00 | 17.81 | 1.14 | 5/3 |
| string.length | 0.0163 | 1.00 | 13.59 | 1.09 | 5/515 |
| method.array.add | 0.0101 | 2.57 | 24.01 | 2.75 | 517/516 |
| method.valuetable.add | 0.0208 | 4.64 | 19.56 | 4.85 | 517/1028 |
| method.valuelist.add | 0.0228 | 3.43 | 13.76 | 3.62 | 517/516 |
### N=4096
| Сценарий | Python мс | Классы × | Bare с компиляцией × | Готовый bare × | Python/C готового bare |
|---|---:|---:|---:|---:|---:|
| method.map.get | 0.2131 | 1.17 | 2.63 | 1.20 | 5/4100 |
| method.map.set | 0.1224 | 1.19 | 3.56 | 1.23 | 5/4 |
| method.map.iterate | 0.1999 | 1.06 | 3.30 | 1.33 | 5/4 |
| method.valuetable.get | 0.1782 | 3.43 | 5.73 | 3.36 | 8197/4 |
| method.valuetable.get_positional | 0.1936 | 1.96 | 3.99 | 1.87 | 4101/4 |
| method.valuetable.iterate | 0.1238 | 3.46 | 6.44 | 3.39 | 4102/4 |
| method.valuelist.get | 0.2320 | 2.19 | 3.86 | 2.15 | 4101/4100 |
| method.valuelist.iterate | 0.1360 | 2.89 | 5.69 | 2.88 | 4101/3 |
| method.array.get | 0.1473 | 1.94 | 3.74 | 2.37 | 4101/4 |
| method.array.set | 0.0636 | 3.50 | 8.25 | 4.32 | 4101/4 |
| method.array.iterate | 0.0901 | 1.01 | 4.20 | 1.23 | 6/4 |
| method.map.insert | 0.1068 | 2.82 | 5.84 | 2.89 | 5/4 |
| assignment | 0.0593 | 1.00 | 4.12 | 1.05 | 5/3 |
| addition | 0.1197 | 0.95 | 2.68 | 0.95 | 5/3 |
| string.length | 0.1452 | 1.05 | 2.68 | 1.00 | 5/4099 |
| method.array.add | 0.0708 | 3.10 | 6.51 | 2.86 | 4101/4100 |
| method.valuetable.add | 0.2447 | 3.95 | 5.65 | 3.79 | 4101/8196 |
| method.valuelist.add | 0.3081 | 2.82 | 4.37 | 2.90 | 4101/4100 |

Не восстановлены: arithmetic, array, byref, calls, map, method.array.create, method.array.delete, method.array.find, method.array.insert, method.map.create, method.map.delete, method.structure.create, method.structure.delete, method.structure.get, method.structure.insert, method.structure.iterate, method.structure.property, method.structure.set, method.valuelist.create, method.valuelist.delete, method.valuelist.find, method.valuelist.insert, method.valuelist.set, method.valuelist.sort, method.valuetable.create, method.valuetable.delete, method.valuetable.find, method.valuetable.insert, method.valuetable.set, method.valuetable.set_positional, method.valuetable.sort, string.concat, string.replace, string.slice

Явный пропуск: method.valuetable.find N4096 во всех слоях.
