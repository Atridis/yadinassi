## Изолированный bare: предварительные реконструированные сценарии

Не production default и не точная копия исторических workloads.
Обычный bare включает компиляцию AST; готовый bare исключает её. Профиль отдельно от времени.
Коммит `40aa72fa269455d0aee19b69ee4957c3ef1cb782`; статусы: {'unbound': 48, 'measured': 364, 'skipped': 4}.
Python = 1×. Короткая серия, общая машина: не гарантия ускорения.

### N=512
| Сценарий | Python мс | Классы × | Bare с компиляцией × | Готовый bare × | Python/C готового bare |
|---|---:|---:|---:|---:|---:|
| method.map.get | 0.0233 | 1.19 | 14.26 | 1.28 | 5/516 |
| method.map.set | 0.0126 | 1.24 | 18.21 | 1.40 | 5/4 |
| method.map.iterate | 0.0233 | 0.96 | 14.24 | 1.49 | 5/4 |
| method.valuetable.get | 0.0193 | 3.73 | 17.10 | 3.67 | 1029/4 |
| method.valuetable.get_positional | 0.0202 | 2.32 | 14.65 | 2.30 | 517/4 |
| method.valuetable.iterate | 0.0149 | 3.47 | 20.73 | 3.75 | 518/4 |
| method.valuelist.get | 0.0209 | 2.86 | 14.59 | 3.02 | 517/516 |
| method.valuelist.iterate | 0.0161 | 2.89 | 17.65 | 3.16 | 517/3 |
| method.array.get | 0.0154 | 2.08 | 18.26 | 2.24 | 517/4 |
| method.array.set | 0.0072 | 3.50 | 33.92 | 3.72 | 517/4 |
| method.array.iterate | 0.0115 | 1.00 | 19.31 | 1.36 | 6/4 |
| method.map.insert | 0.0125 | 3.03 | 19.88 | 3.13 | 5/4 |
| assignment | 0.0066 | 1.00 | 26.83 | 1.25 | 5/3 |
| addition | 0.0129 | 1.01 | 14.72 | 1.11 | 5/3 |
| string.length | 0.0166 | 0.98 | 12.91 | 1.08 | 5/515 |
| method.array.add | 0.0101 | 2.59 | 26.69 | 2.72 | 517/516 |
| method.valuetable.add | 0.0207 | 4.71 | 16.88 | 4.84 | 517/1028 |
| method.valuelist.add | 0.0224 | 3.47 | 13.80 | 3.57 | 517/516 |
| method.array.create | 0.0110 | 5.69 | 23.77 | 5.90 | 517/3 |
| method.array.find | 1.0173 | 0.93 | 1.26 | 0.93 | 517/516 |
| method.array.insert | 0.0450 | 1.35 | 6.89 | 1.40 | 517/516 |
| method.array.delete | 0.0265 | 1.58 | 10.57 | 1.66 | 517/4 |
| method.structure.create | 0.0108 | 9.15 | 24.82 | 9.27 | 517/515 |
| method.structure.insert | 0.0108 | 4.59 | 23.62 | 4.68 | 517/516 |
| method.structure.get | 0.0143 | 1.62 | 16.67 | 1.74 | 5/516 |
| method.structure.set | 0.0111 | 3.36 | 23.85 | 3.42 | 5/4 |
| method.structure.property | 0.0168 | 3.69 | 19.34 | 3.79 | 517/516 |
| method.structure.delete | 0.0136 | 3.75 | 20.83 | 3.91 | 517/1028 |
| method.structure.iterate | 0.0140 | 10.03 | 26.86 | 12.56 | 1030/516 |
| calls | 0.0309 | 0.98 | 9.49 | 1.05 | 517/3 |
| byref | 0.0343 | 1.00 | 8.24 | 1.03 | 517/3 |
| method.map.create | 0.0108 | 3.03 | 19.77 | 3.12 | 5/3 |
| method.map.delete | 0.0228 | 2.03 | 12.01 | 2.07 | 517/516 |
| method.valuelist.create | 0.0108 | 2.68 | 17.86 | 2.79 | 5/3 |
| method.valuelist.delete | 0.0350 | 1.82 | 8.61 | 1.91 | 5/4 |
| method.valuelist.insert | 0.0590 | 1.91 | 5.90 | 1.95 | 517/516 |
| method.valuelist.set | 0.0113 | 4.18 | 25.29 | 4.40 | 517/516 |
| method.valuelist.sort | 0.0244 | 1.34 | 6.30 | 1.32 | 518/3 |
| method.valuelist.find | 2.7690 | 1.60 | 1.77 | 1.60 | 2053/516 |
| method.valuetable.create | 0.0508 | 2.82 | 8.01 | 2.89 | 1029/1027 |
| method.valuetable.delete | 0.0338 | 1.78 | 10.73 | 1.84 | 517/4 |
| method.valuetable.insert | 0.0558 | 2.63 | 7.94 | 2.51 | 517/1028 |
| method.valuetable.set | 0.0114 | 4.94 | 27.38 | 5.14 | 1029/4 |
| method.valuetable.set_positional | 0.0113 | 4.72 | 32.15 | 3.04 | 517/4 |
| method.valuetable.sort | 0.0230 | 1.39 | 7.20 | 1.52 | 518/4 |
| method.valuetable.find | 2.7133 | 1.49 | 1.63 | 1.51 | 1029/516 |
### N=4096
| Сценарий | Python мс | Классы × | Bare с компиляцией × | Готовый bare × | Python/C готового bare |
|---|---:|---:|---:|---:|---:|
| method.map.get | 0.2107 | 1.18 | 3.03 | 1.28 | 5/4100 |
| method.map.set | 0.1222 | 1.19 | 3.01 | 1.20 | 5/4 |
| method.map.iterate | 0.1974 | 0.96 | 3.12 | 1.36 | 5/4 |
| method.valuetable.get | 0.1710 | 3.52 | 5.56 | 3.77 | 8197/4 |
| method.valuetable.get_positional | 0.1771 | 2.26 | 4.08 | 2.13 | 4101/4 |
| method.valuetable.iterate | 0.1271 | 3.19 | 5.73 | 3.34 | 4102/4 |
| method.valuelist.get | 0.1921 | 2.65 | 4.43 | 2.54 | 4101/4100 |
| method.valuelist.iterate | 0.1311 | 2.95 | 5.57 | 2.96 | 4101/3 |
| method.array.get | 0.1425 | 1.90 | 3.76 | 2.06 | 4101/4 |
| method.array.set | 0.0692 | 3.11 | 7.35 | 3.88 | 4101/4 |
| method.array.iterate | 0.0935 | 0.97 | 3.70 | 1.18 | 6/4 |
| method.map.insert | 0.1031 | 3.13 | 5.66 | 2.90 | 5/4 |
| assignment | 0.0582 | 1.00 | 3.93 | 1.03 | 5/3 |
| addition | 0.1129 | 1.04 | 2.77 | 1.04 | 5/3 |
| string.length | 0.1512 | 0.96 | 2.88 | 1.02 | 5/4099 |
| method.array.add | 0.0696 | 2.83 | 6.36 | 2.85 | 4101/4100 |
| method.valuetable.add | 0.2454 | 3.93 | 5.14 | 3.88 | 4101/8196 |
| method.valuelist.add | 0.3404 | 2.47 | 3.77 | 2.60 | 4101/4100 |
| method.array.create | 0.0972 | 5.63 | 7.34 | 5.64 | 4101/3 |
| method.array.find | 66.3827 | 1.01 | 1.02 | 1.00 | 4101/4100 |
| method.array.insert | 1.8825 | 1.11 | 1.23 | 1.07 | 4101/4100 |
| method.array.delete | 0.2714 | 1.56 | 2.47 | 1.48 | 4101/4 |
| method.structure.create | 0.0952 | 9.06 | 11.11 | 8.89 | 4101/4099 |
| method.structure.insert | 0.0980 | 4.56 | 7.21 | 4.89 | 4101/4100 |
| method.structure.get | 0.1380 | 1.49 | 3.42 | 1.50 | 5/4100 |
| method.structure.set | 0.0992 | 3.07 | 5.34 | 3.29 | 5/4 |
| method.structure.property | 0.1529 | 3.42 | 5.19 | 3.58 | 4101/4100 |
| method.structure.delete | 0.1149 | 3.77 | 6.16 | 3.83 | 4101/8196 |
| method.structure.iterate | 0.1092 | 10.78 | 13.61 | 10.80 | 8198/4100 |
| calls | 0.3257 | 0.93 | 1.64 | 0.93 | 4101/3 |
| byref | 0.2898 | 1.02 | 2.16 | 1.14 | 4101/3 |
| method.map.create | 0.0939 | 2.84 | 5.22 | 2.93 | 5/3 |
| method.map.delete | 0.2278 | 1.87 | 3.21 | 1.88 | 4101/4100 |
| method.valuelist.create | 0.0963 | 2.93 | 4.67 | 2.52 | 5/3 |
| method.valuelist.delete | 0.3434 | 1.72 | 2.54 | 1.61 | 5/4 |
| method.valuelist.insert | 2.1453 | 1.23 | 1.39 | 1.29 | 4101/4100 |
| method.valuelist.set | 0.1153 | 3.33 | 6.43 | 3.40 | 4101/4100 |
| method.valuelist.sort | 0.2358 | 1.17 | 2.16 | 1.15 | 4102/3 |
| method.valuelist.find | 193.1426 | 1.64 | 1.56 | 1.67 | 16389/4100 |
| method.valuetable.create | 0.4082 | 3.07 | 3.91 | 3.03 | 8197/8195 |
| method.valuetable.delete | 0.3637 | 1.50 | 2.36 | 1.49 | 4101/4 |
| method.valuetable.insert | 2.0760 | 1.36 | 1.51 | 1.40 | 4101/8196 |
| method.valuetable.set | 0.1077 | 4.34 | 7.51 | 4.51 | 8197/4 |
| method.valuetable.set_positional | 0.1055 | 4.24 | 5.98 | 2.69 | 4101/4 |
| method.valuetable.sort | 0.2037 | 1.28 | 2.47 | 1.28 | 4102/4 |

Не восстановлены: arithmetic, array, map, string.concat, string.replace, string.slice

Явный пропуск: method.valuetable.find N4096 во всех слоях.
