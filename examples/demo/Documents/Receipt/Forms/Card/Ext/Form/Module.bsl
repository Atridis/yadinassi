&НаСервере
Процедура Created(Cancel, StandardProcessing)
 Если Object.Number = "" Тогда Object.Date = Дата(2026, 11, 11, 12, 0, 0); КонецЕсли;
 Dirty = Ложь;
 Status = "";
КонецПроцедуры
&НаКлиенте
Процедура AddLineCommand(Command)
 AddAtServer();
КонецПроцедуры
&НаСервере
Процедура AddAtServer()
 Row = Object.Lines.Add();
 Row.Quantity = 1;
 Row.Amount = 0;
 Dirty = Истина;
 Status = "";
КонецПроцедуры
&НаКлиенте
Процедура DeleteLineCommand(Command)
 DeleteAtServer();
КонецПроцедуры
&НаСервере
Процедура DeleteAtServer()
 Row = Items.LinesTable.CurrentData;
 Если Row <> Неопределено Тогда Object.Lines.Delete(Row); Dirty = Истина; КонецЕсли;
КонецПроцедуры
&НаКлиенте
Процедура WriteCommand(Command)
КонецПроцедуры
&НаКлиенте
Процедура PostCommand(Command)
КонецПроцедуры
&НаКлиенте
Процедура UndoPostingCommand(Command)
КонецПроцедуры
&НаКлиенте
Процедура Changed(Element)
 Dirty = Истина;
 Status = "";
КонецПроцедуры
&НаКлиенте
Процедура BeforeClose(Cancel, Exit, MessageText, StandardProcessing)
 // Доверенный хост сравнивает полный типизированный образ и квитанцию операции.
 // Флаг интерфейса не доказывает сохранение и не разрешает повтор операции.
КонецПроцедуры
