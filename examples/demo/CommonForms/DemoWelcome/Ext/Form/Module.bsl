&НаСервере
Процедура Created(Cancel, StandardProcessing)
 Greeting = "Справочники, документы и регистр накопления работают в одной базе";
КонецПроцедуры
&НаКлиенте
Процедура ShowDetails(Command)
 Сообщить(DemoService.Add(4));
 DemoTools.OpenOperation();
КонецПроцедуры
