## Изолированный bare: предварительные реконструированные сценарии

Не production default и не точная копия исторических workloads.
Обычный bare включает компиляцию AST; готовый bare исключает её. Профиль отдельно от времени.
Коммит `1670c9dc28bf4a4869f6e7b223816c84a3e78111`; статусы: {'measured': 412, 'skipped': 4}.
Python = 1×. Короткая серия, общая машина: не гарантия ускорения.

### N=512
| Сценарий | Python мс | Классы × | Bare с компиляцией × | Готовый bare × | Python/C готового bare |
|---|---:|---:|---:|---:|---:|
| method.map.get | 0.0231 | 1.23 | 14.24 | 1.27 | 5/516 |
| method.map.set | 0.0129 | 1.19 | 23.86 | 1.33 | 5/4 |
| method.map.iterate | 0.0279 | 0.84 | 10.89 | 1.28 | 5/4 |
| method.valuetable.get | 0.0198 | 3.59 | 17.41 | 3.55 | 1029/4 |
| method.valuetable.get_positional | 0.0195 | 2.47 | 18.59 | 2.34 | 517/4 |
| method.valuetable.iterate | 0.0150 | 3.45 | 25.40 | 3.85 | 518/4 |
| method.valuelist.get | 0.0214 | 2.87 | 15.48 | 2.93 | 517/516 |
| method.valuelist.iterate | 0.0161 | 2.91 | 22.37 | 3.20 | 517/3 |
| method.array.get | 0.0155 | 2.07 | 17.59 | 2.20 | 517/4 |
| method.array.set | 0.0073 | 3.42 | 34.90 | 3.66 | 517/4 |
| method.array.iterate | 0.0113 | 1.02 | 26.59 | 1.40 | 6/4 |
| method.map.insert | 0.0126 | 3.02 | 21.69 | 3.14 | 5/4 |
| assignment | 0.0065 | 0.98 | 30.16 | 1.24 | 5/3 |
| addition | 0.0131 | 1.00 | 17.30 | 1.17 | 5/3 |
| string.length | 0.0169 | 0.98 | 13.37 | 1.07 | 5/515 |
| method.array.add | 0.0102 | 2.56 | 24.04 | 2.72 | 517/516 |
| method.valuetable.add | 0.0214 | 4.58 | 17.13 | 4.70 | 517/1028 |
| method.valuelist.add | 0.0226 | 3.82 | 16.50 | 3.63 | 517/516 |
| method.array.create | 0.0109 | 5.90 | 22.42 | 6.03 | 517/3 |
| method.array.find | 0.9685 | 1.08 | 1.31 | 1.17 | 517/516 |
| method.array.insert | 0.0451 | 1.36 | 6.75 | 1.41 | 517/516 |
| method.array.delete | 0.0264 | 1.68 | 11.48 | 1.71 | 517/4 |
| method.structure.create | 0.0108 | 9.12 | 25.81 | 9.20 | 517/515 |
| method.structure.insert | 0.0111 | 4.50 | 26.07 | 4.73 | 517/516 |
| method.structure.get | 0.0144 | 1.63 | 17.49 | 1.73 | 5/516 |
| method.structure.set | 0.0108 | 3.32 | 24.09 | 3.44 | 5/4 |
| method.structure.property | 0.0170 | 3.75 | 19.80 | 3.91 | 517/516 |
| method.structure.delete | 0.0138 | 3.72 | 39.43 | 3.85 | 517/1028 |
| method.structure.iterate | 0.0147 | 9.69 | 27.39 | 1.75 | 5/4 |
| calls | 0.0309 | 0.99 | 10.29 | 1.08 | 517/3 |
| byref | 0.0345 | 0.98 | 12.98 | 1.08 | 517/3 |
| method.map.create | 0.0111 | 2.99 | 19.71 | 3.08 | 5/3 |
| method.map.delete | 0.0235 | 1.98 | 13.22 | 4.04 | 517/516 |
| method.valuelist.create | 0.0108 | 2.68 | 18.97 | 2.91 | 5/3 |
| method.valuelist.delete | 0.0363 | 1.79 | 10.65 | 2.23 | 5/4 |
| method.valuelist.insert | 0.0579 | 1.94 | 6.66 | 1.98 | 517/516 |
| method.valuelist.set | 0.0117 | 4.03 | 26.72 | 4.28 | 517/516 |
| method.valuelist.sort | 0.0240 | 1.26 | 8.90 | 1.34 | 518/3 |
| method.valuelist.find | 2.7618 | 1.67 | 1.85 | 1.72 | 2053/516 |
| method.valuetable.create | 0.0502 | 3.11 | 7.72 | 3.14 | 1029/1027 |
| method.valuetable.delete | 0.0353 | 1.70 | 10.63 | 1.75 | 517/4 |
| method.valuetable.insert | 0.0563 | 2.45 | 8.09 | 2.48 | 517/1028 |
| method.valuetable.set | 0.0115 | 4.90 | 31.94 | 5.13 | 1029/4 |
| method.valuetable.set_positional | 0.0116 | 4.65 | 24.30 | 3.06 | 517/4 |
| method.valuetable.sort | 0.0233 | 1.42 | 7.76 | 1.48 | 518/4 |
| method.valuetable.find | 2.6494 | 1.54 | 1.67 | 1.58 | 1029/516 |
| arithmetic | 0.0330 | 1.00 | 7.92 | 1.06 | 5/3 |
| string.concat | 0.0178 | 0.97 | 11.85 | 1.07 | 5/3 |
| array | 0.0207 | 1.78 | 17.87 | 2.01 | 518/518 |
| map | 0.0255 | 6.91 | 16.28 | 2.44 | 5/6 |
| string.slice | 0.0296 | 0.99 | 7.73 | 1.05 | 5/3 |
| string.replace | 0.0400 | 1.03 | 6.74 | 1.15 | 5/515 |
### N=4096
| Сценарий | Python мс | Классы × | Bare с компиляцией × | Готовый bare × | Python/C готового bare |
|---|---:|---:|---:|---:|---:|
| method.map.get | 0.2174 | 1.17 | 2.82 | 1.19 | 5/4100 |
| method.map.set | 0.1216 | 1.20 | 3.55 | 1.21 | 5/4 |
| method.map.iterate | 0.2674 | 0.70 | 2.38 | 1.29 | 5/4 |
| method.valuetable.get | 0.2041 | 3.85 | 5.58 | 3.08 | 8197/4 |
| method.valuetable.get_positional | 0.2866 | 1.49 | 2.98 | 1.57 | 4101/4 |
| method.valuetable.iterate | 0.1241 | 3.24 | 7.29 | 3.48 | 4102/4 |
| method.valuelist.get | 0.2485 | 2.14 | 3.58 | 2.35 | 4101/4100 |
| method.valuelist.iterate | 0.1296 | 3.47 | 6.04 | 3.29 | 4101/3 |
| method.array.get | 0.1420 | 2.28 | 4.61 | 2.33 | 4101/4 |
| method.array.set | 0.0649 | 3.63 | 7.16 | 3.42 | 4101/4 |
| method.array.iterate | 0.0906 | 1.02 | 4.65 | 1.17 | 6/4 |
| method.map.insert | 0.1034 | 2.97 | 6.10 | 3.37 | 5/4 |
| assignment | 0.0592 | 0.99 | 4.11 | 1.01 | 5/3 |
| addition | 0.1129 | 1.28 | 3.62 | 1.02 | 5/3 |
| string.length | 0.1575 | 0.93 | 2.50 | 0.93 | 5/4099 |
| method.array.add | 0.0721 | 2.75 | 9.58 | 2.83 | 4101/4100 |
| method.valuetable.add | 0.2355 | 4.46 | 5.81 | 4.57 | 4101/8196 |
| method.valuelist.add | 0.2926 | 2.93 | 4.50 | 3.43 | 4101/4100 |
| method.array.create | 0.0962 | 5.67 | 7.91 | 5.66 | 4101/3 |
| method.array.find | 73.2177 | 0.99 | 0.95 | 0.96 | 4101/4100 |
| method.array.insert | 1.9409 | 1.45 | 2.13 | 1.94 | 4101/4100 |
| method.array.delete | 0.2988 | 1.35 | 3.01 | 1.34 | 4101/4 |
| method.structure.create | 0.0950 | 8.59 | 10.74 | 8.51 | 4101/4099 |
| method.structure.insert | 0.0986 | 4.61 | 8.79 | 4.58 | 4101/4100 |
| method.structure.get | 0.1388 | 1.49 | 3.64 | 1.51 | 5/4100 |
| method.structure.set | 0.0990 | 3.08 | 5.65 | 3.03 | 5/4 |
| method.structure.property | 0.1559 | 3.41 | 5.33 | 3.40 | 4101/4100 |
| method.structure.delete | 0.1089 | 3.95 | 6.44 | 4.41 | 4101/8196 |
| method.structure.iterate | 0.1330 | 12.16 | 5.72 | 1.41 | 5/4 |
| calls | 0.3209 | 1.27 | 2.11 | 0.85 | 4101/3 |
| byref | 0.4328 | 0.78 | 1.67 | 0.81 | 4101/3 |
| method.map.create | 0.0974 | 4.23 | 5.60 | 2.87 | 5/3 |
| method.map.delete | 0.4558 | 1.84 | 2.75 | 1.83 | 4101/4100 |
| method.valuelist.create | 0.0970 | 3.07 | 6.53 | 2.89 | 5/3 |
| method.valuelist.delete | 0.4204 | 1.48 | 2.37 | 1.50 | 5/4 |
| method.valuelist.insert | 2.2192 | 1.28 | 1.46 | 1.29 | 4101/4100 |
| method.valuelist.set | 0.1152 | 3.34 | 7.73 | 4.00 | 4101/4100 |
| method.valuelist.sort | 0.2631 | 1.03 | 2.09 | 1.12 | 4102/3 |
| method.valuelist.find | 214.4793 | 1.61 | 1.76 | 1.60 | 16389/4100 |
| method.valuetable.create | 0.4053 | 3.11 | 3.64 | 2.97 | 8197/8195 |
| method.valuetable.delete | 0.3511 | 1.62 | 2.46 | 1.58 | 4101/4 |
| method.valuetable.insert | 2.3963 | 1.38 | 1.43 | 1.29 | 4101/8196 |
| method.valuetable.set | 0.1109 | 4.32 | 8.14 | 4.52 | 8197/4 |
| method.valuetable.set_positional | 0.1083 | 4.35 | 6.09 | 2.51 | 4101/4 |
| method.valuetable.sort | 0.2163 | 1.26 | 2.34 | 1.21 | 4102/4 |
| arithmetic | 0.2845 | 1.00 | 2.02 | 1.08 | 5/3 |
| string.concat | 0.1583 | 0.99 | 2.44 | 1.00 | 5/3 |
| array | 0.1646 | 1.79 | 4.31 | 1.89 | 4102/4102 |
| map | 0.2157 | 6.59 | 4.04 | 2.33 | 5/6 |
| string.slice | 0.2642 | 0.96 | 1.90 | 1.11 | 5/3 |
| string.replace | 0.3270 | 1.03 | 1.98 | 1.18 | 5/4099 |

Не восстановлены: нет

Явный пропуск: method.valuetable.find N4096 во всех слоях.
