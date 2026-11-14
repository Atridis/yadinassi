&НаКлиенте
Перем PendingDraft;
&НаСервере
Процедура Created(Cancel, StandardProcessing)
 DraftTitle = "Новая операция";
 Amount = 0;
 Comment = "";
 AppliedCount = 0;
 LastOutcome = "Изменения не подготовлены";
КонецПроцедуры
&НаКлиенте
Процедура EditDraft(Command)
 Если PendingDraft <> Неопределено Тогда
  DraftSnapshot = Новый Структура("DraftTitle,Amount,Comment", PendingDraft.DraftTitle, PendingDraft.Amount, PendingDraft.Comment);
 Иначе
  DraftSnapshot = Новый Структура("DraftTitle,Amount,Comment", DraftTitle, Amount, Comment);
 КонецЕсли;
 ОткрытьФорму("CommonForm.DraftDetails", DraftSnapshot, ThisObject,
  Неопределено, Неопределено, Неопределено, Новый ОписаниеОповещения("DetailsCompleted", ThisObject));
КонецПроцедуры
&НаКлиенте
Процедура DetailsCompleted(Result, AdditionalParameters) Экспорт
 Если Result <> Неопределено Тогда
  PendingDraft = Result;
  LastOutcome = "Черновик ожидает подтверждения";
 Иначе
  LastOutcome = "Редактирование отменено";
 КонецЕсли;
КонецПроцедуры
&НаКлиенте
Процедура ConfirmDraft(Command)
 Если PendingDraft = Неопределено Тогда
  LastOutcome = "Нет подготовленных изменений";
 Иначе
  ПоказатьВопрос(Новый ОписаниеОповещения("QuestionCompleted", ThisObject), "Применить подготовленные изменения?", QuestionDialogMode.YesNoCancel,
   Неопределено, Неопределено, "Подтверждение черновика");
 КонецЕсли;
КонецПроцедуры
&НаКлиенте
Процедура QuestionCompleted(Result, AdditionalParameters) Экспорт
 Если Result = DialogReturnCode.Yes Тогда
  Если PendingDraft <> Неопределено Тогда
   DraftTitle = PendingDraft.DraftTitle;
   Amount = PendingDraft.Amount;
   Comment = PendingDraft.Comment;
   AppliedCount = AppliedCount + 1;
   PendingDraft = Неопределено;
   LastOutcome = "Черновик применён";
  КонецЕсли;
 ИначеЕсли Result = DialogReturnCode.No Тогда
  PendingDraft = Неопределено;
  LastOutcome = "Подготовленные изменения отклонены";
 Иначе
  LastOutcome = "Решение отложено";
 КонецЕсли;
КонецПроцедуры
&НаКлиенте
Процедура ShowInfo(Command)
 ПоказатьПредупреждение(Новый ОписаниеОповещения("InfoCompleted", ThisObject), "Это черновик в памяти формы. Документы и движения в базе не записываются.", Неопределено, "Операция без записи");
КонецПроцедуры
&НаКлиенте
Процедура InfoCompleted(AdditionalParameters) Экспорт
 LastOutcome = "Информация просмотрена";
КонецПроцедуры
