&НаСервере
Процедура Created(Cancel, StandardProcessing)
 Если Parameters.Property("DraftTitle") Тогда DraftTitle = Parameters.DraftTitle; КонецЕсли;
 Если Parameters.Property("Amount") Тогда Amount = Parameters.Amount; КонецЕсли;
 Если Parameters.Property("Comment") Тогда Comment = Parameters.Comment; КонецЕсли;
КонецПроцедуры
&НаКлиенте
Процедура AcceptDraft(Command)
 Закрыть(Новый Структура("DraftTitle,Amount,Comment", DraftTitle, Amount, Comment));
КонецПроцедуры
&НаКлиенте
Процедура CancelDraft(Command)
 Закрыть(Неопределено);
КонецПроцедуры
&НаКлиенте
Процедура Closing(Cancel, Quitting, Warning, StandardProcessing)
 Если KeepOpen Тогда
  Cancel = Истина;
  Сообщить("Снимите флажок KeepOpen, чтобы закрыть черновик");
 КонецЕсли;
КонецПроцедуры
