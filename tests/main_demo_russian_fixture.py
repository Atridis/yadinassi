"""Test-only correspondence of current Russian captions to historical layout fingerprints."""
RUSSIAN_TITLES = {'Receipt card': 'Поступление',
 'Issue card': 'Списание',
 'Document number': 'Номер документа',
 'Date and time': 'Дата и время',
 'Warehouse': 'Склад',
 'Marked for deletion': 'Пометка удаления',
 'Authoritative Posted state': 'Проведён',
 'Product lines': 'Товары',
 'Add line': 'Добавить строку',
 'Delete selected line': 'Удалить строку',
 'Write document': 'Записать',
 'Post document': 'Провести',
 'Undo posting': 'Отменить проведение',
 'Status': 'Статус',
 'State': 'Состояние',
 'Product': 'Номенклатура',
 'Quantity': 'Количество',
 'Amount': 'Сумма',
 'Unit': 'Единица измерения',
 'DraftTitle': 'Заголовок',
 'Comment': 'Комментарий',
 'AppliedCount': 'Число применений',
 'LastOutcome': 'Результат',
 'KeepOpen': 'Не закрывать форму'}

def historical_titles(raw):
    for english, russian in RUSSIAN_TITLES.items():
        raw = raw.replace(('<Title>'+russian+'</Title>').encode(), ('<Title>'+english+'</Title>').encode())
    return raw
