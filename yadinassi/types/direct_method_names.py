"""Namespace used for methods exposed to generated BSL calls."""


class DirectMethodNames:
    __slots__ = ()

    def __getattr__(self, name):
        if name.startswith('_bsl_value_'):
            procedure = '_bsl_proc_' + name.removeprefix('_bsl_value_')
            if procedure in vars(type(self)):
                raise TypeError('Процедура не возвращает значение')
        if name.startswith('_bsl_'):
            raise ValueError('Метод или свойство не найдено: ' + name.split('_', 3)[-1])
        raise AttributeError(name)
