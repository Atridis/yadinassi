// One ordinary XML workflow batch; only synthetic strings and fresh owned temporary files.
// !todo DTD/schema/XDTO/streams and rare lexical/namespace corners remain deferred.
Функция XFEncode(Знач Text)
    Если ТипЗнч(Text) <> Тип("Строка") Или СтрДлина(Text) > 56 Тогда
        ВызватьИсключение "xml-observer-text-bound";
    КонецЕсли;
    Record = "S" + Строка(СтрДлина(Text)) + ":";
    Для P = 1 По СтрДлина(Text) Цикл
        Code = КодСимвола(Text, P);
        Если Code < 0 Или Code > 65535 Тогда ВызватьИсключение "xml-observer-unit-bound"; КонецЕсли;
        Digits = "";
        Для D = 1 По 4 Цикл
            Quotient = Цел(Code / 16);
            Digits = Сред("0123456789abcdef", Code - Quotient * 16 + 1, 1) + Digits;
            Code = Quotient;
        КонецЦикла;
        Record = Record + Digits;
    КонецЦикла;
    Возврат Record;
КонецФункции
Функция XFToken(Знач R)
    T = R.NodeType;
    Если T = XMLNodeType.StartElement Тогда Возврат "S"; КонецЕсли;
    Если T = XMLNodeType.EndElement Тогда Возврат "E"; КонецЕсли;
    Если T = XMLNodeType.Text Тогда Возврат "T"; КонецЕсли;
    Если T = XMLNodeType.CDATASection Тогда Возврат "D"; КонецЕсли;
    Если T = XMLNodeType.Comment Тогда Возврат "C"; КонецЕсли;
    Если T = XMLNodeType.ProcessingInstruction Тогда Возврат "P"; КонецЕсли;
    Возврат "?";
КонецФункции
Функция XFOwnedFile(Знач Encoding, Знач BOM)
    Root = GetTempFileName("xml-workflow"); F = Новый File(Root);
    Если F.Exists() Тогда ВызватьИсключение "xml-fixture-collision"; КонецЕсли;
    R = Новый XMLReader; W = Новый XMLWriter;
    CreateDirectory(Root); Path = Root + "/a.xml";
    Попытка
        W.OpenFile(Path, Encoding, BOM); W.WriteXMLDeclaration();
        W.WriteStartElement("r"); W.WriteAttribute("a", "1"); W.WriteText("я"); W.WriteEndElement();
        Closed = W.Close(); R.OpenFile(Path); R.MoveToContent();
        A = R.GetAttribute("a"); R.Read(); Value = R.Value;
        R.Close(); DeleteFiles(Path);
        Remaining = FindFiles(Root, "*");
        Если Remaining.Count() <> 0 Тогда ВызватьИсключение "xml-fixture-not-empty"; КонецЕсли;
        DeleteFiles(Root);
        Если F.Exists() Тогда ВызватьИсключение "xml-fixture-cleanup"; КонецЕсли;
    Исключение
        Попытка R.Close(); Исключение КонецПопытки;
        Попытка W.Close(); Исключение КонецПопытки;
        Попытка DeleteFiles(Path); Исключение КонецПопытки;
        Попытка
            Remaining = FindFiles(Root, "*");
            Если Remaining.Count() = 0 Тогда DeleteFiles(Root); КонецЕсли;
        Исключение КонецПопытки;
        ВызватьИсключение;
    КонецПопытки;
    Возврат Строка(СтрДлина(Closed)) + ":" + A + ":" + Value;
КонецФункции
Функция XFCase(Знач N)
    R = Новый XMLReader; W = Новый XMLWriter;
    Если N = 1 Тогда
        R.SetString("<r><a>я</a><b/></r>"); S = ""; Пока R.Read() Цикл S = S + XFToken(R) + ":" + R.Name + ":" + R.Value + ";"; КонецЦикла; Возврат S;
    ИначеЕсли N = 2 Тогда
        R.SetString("<r a=""1"" b=""я""/>"); R.Read(); Возврат Строка(R.AttributeCount()) + ":" + R.AttributeName(0) + ":" + R.AttributeValue(1) + ":" + R.GetAttribute("a");
    ИначеЕсли N = 3 Тогда
        R.SetString("<r xmlns:p=""urn:p"" p:a=""v""/>"); R.Read(); Возврат R.AttributeValue("a", "urn:p") + ":" + R.GetAttribute("p:a") + ":" + Строка(R.GetAttribute("missing") = Неопределено);
    ИначеЕсли N = 4 Тогда
        R.SetString("<p:r xmlns:p=""urn:p""/>"); R.Read(); Возврат R.Name + ":" + R.LocalName + ":" + R.Prefix + ":" + R.NamespaceURI;
    ИначеЕсли N = 5 Тогда
        R.SetString("<r xmlns=""urn:d""><x/></r>"); R.Read(); R.Read(); Возврат R.Name + ":" + R.Prefix + ":" + R.NamespaceURI;
    ИначеЕсли N = 6 Тогда
        R.SetString("<r a=""1"" b=""2""/>"); R.Read(); S = ""; Пока R.ReadAttribute() Цикл S = S + R.Name + "=" + R.Value + ";"; КонецЦикла; Возврат S;
    ИначеЕсли N = 7 Тогда
        R.SetString("<r a=""1"" b=""2""/>"); R.Read(); A = R.FirstAttribute(); X = R.Name; B = R.NextAttribute(); Возврат Строка(A) + ":" + X + ":" + Строка(B) + ":" + R.Name;
    ИначеЕсли N = 8 Тогда
        R.SetString("<r><a><b/></a><c/></r>"); R.Read(); R.Read(); R.Skip(); Возврат XFToken(R) + ":" + R.Name;
    ИначеЕсли N = 9 Тогда
        R.SetString("<?xml version=""1.0""?><!--c--><r> <a/></r>"); Before = R.IgnoreWhitespace; T = R.MoveToContent(); R.IgnoreWhitespace = Ложь; R.Read(); Space = R.IsWhitespace; R.IgnoreWhitespace = Истина; R.Read(); Возврат Строка(Before) + ":" + Строка(T = XMLNodeType.StartElement) + ":" + Строка(Space) + ":" + R.Name;
    ИначеЕсли N = 10 Тогда
        R.SetString("<r>&lt;&amp;&#x41;</r>", Новый XMLReaderSettings); R.Read(); R.Read(); Возврат R.Value;
    ИначеЕсли N = 11 Тогда
        R.SetString("<r><![CDATA[a<b]]><!--c--><?pi x?></r>"); R.Read(); S = ""; Пока R.Read() Цикл S = S + XFToken(R) + ":" + R.Value + ";"; КонецЦикла; Возврат S;
    ИначеЕсли N = 12 Тогда
        R.SetString("<r/>"); Пока R.Read() Цикл КонецЦикла; Возврат Строка(R.Read()) + ":" + Строка(R.NodeType = XMLNodeType.None);
    ИначеЕсли N = 13 Тогда
        W.SetString(); W.WriteStartElement("r"); W.WriteEndElement(); Возврат W.Close();
    ИначеЕсли N = 14 Тогда
        W.SetString(); W.WriteStartElement("r"); W.WriteText("<&>я"); W.WriteEndElement(); Возврат W.Close();
    ИначеЕсли N = 15 Тогда
        W.SetString(); W.WriteStartElement("r"); W.WriteAttribute("a", "<&"""); W.WriteEndElement(); Возврат W.Close();
    ИначеЕсли N = 16 Тогда
        W.SetString(); W.WriteStartElement("r"); W.WriteStartAttribute("a"); W.WriteText("x&"); W.WriteText("y"); W.WriteEndAttribute(); W.WriteEndElement(); Возврат W.Close();
    ИначеЕсли N = 17 Тогда
        W.SetString(Новый XMLWriterSettings(, , Ложь)); W.WriteStartElement("r"); W.WriteStartElement("a"); W.WriteText("x"); W.WriteEndElement(); W.WriteEndElement(); Возврат W.Close();
    ИначеЕсли N = 18 Тогда
        W.SetString(); W.WriteXMLDeclaration(); W.WriteStartElement("r"); W.WriteEndElement(); Возврат W.Close();
    ИначеЕсли N = 19 Тогда
        W.SetString("UTF-8"); W.WriteXMLDeclaration(); W.WriteStartElement("r"); W.WriteEndElement(); Возврат W.Close();
    ИначеЕсли N = 20 Тогда
        W.SetString(); W.WriteStartElement("r"); W.WriteCDATASection("a<b"); W.WriteComment("c"); W.WriteEndElement(); Возврат W.Close();
    ИначеЕсли N = 21 Тогда
        W.SetString(); W.WriteProcessingInstruction("pi", "x"); W.WriteStartElement("r"); W.WriteEndElement(); Возврат W.Close();
    ИначеЕсли N = 22 Тогда
        W.SetString(); W.WriteStartElement("r"); W.WriteNamespaceMapping("p", "urn:p"); W.WriteAttribute("a", "urn:p", "v"); W.WriteEndElement(); Возврат W.Close();
    ИначеЕсли N = 23 Тогда
        W.SetString(); W.WriteStartElement("r", "urn:d"); W.WriteNamespaceMapping("", "urn:d"); W.WriteEndElement(); Возврат W.Close();
    ИначеЕсли N = 24 Тогда
        W.SetString(); W.WriteStartElement("r"); W.WriteNamespaceMapping("p", "urn:p"); X = W.LookupPrefix("urn:p"); W.WriteEndElement(); Возврат X;
    ИначеЕсли N = 25 Тогда
        W.SetString(); W.WriteStartElement("r"); W.WriteRaw("<a>ok</a>"); W.WriteEndElement(); Возврат W.Close();
    ИначеЕсли N = 26 Тогда
        R.SetString("<r a=""1""><x>я</x></r>"); W.SetString(); Пока R.Read() Цикл W.WriteCurrent(R); КонецЦикла; Возврат W.Close();
    ИначеЕсли N = 27 Тогда
        Возврат XFOwnedFile("UTF-8", Истина);
    ИначеЕсли N = 28 Тогда
        Возврат XFOwnedFile("UTF-16", Истина);
    ИначеЕсли N = 29 Тогда
        Возврат XFOwnedFile("UTF-8", Ложь);
    ИначеЕсли N = 30 Тогда
        R.SetString("<a/>"); R.Read(); R.Close(); R.SetString("<b/>"); R.Read(); W.SetString(); W.WriteStartElement(R.Name); W.WriteEndElement(); X = W.Close(); W.SetString(); W.WriteStartElement("c"); W.WriteEndElement(); Возврат X + ":" + W.Close();
    ИначеЕсли N = 31 Тогда
        Возврат Строка(ТипЗнч(R) = Тип("XMLReader")) + ":" + Строка(ТипЗнч(W) = Тип("XMLWriter")) + ":" + Строка(ТипЗнч(XMLNodeType.Text) = Тип("XMLNodeType")) + ":" + Строка(ТипЗнч(Новый XMLReaderSettings) = Тип("XMLReaderSettings")) + ":" + Строка(ТипЗнч(Новый XMLWriterSettings) = Тип("XMLWriterSettings"));
    ИначеЕсли N = 32 Тогда
        Попытка R.SetString("<a></b>"); Пока R.Read() Цикл КонецЦикла; Исключение Возврат "parse-error"; КонецПопытки; Возврат "unexpected-success";
    ИначеЕсли N = 33 Тогда
        W.SetString(); W.WriteStartElement("r"); W.WriteText("x"); Попытка W.WriteAttribute("a", "v"); Исключение Возврат "attribute-error"; КонецПопытки; Возврат "unexpected-success";
    КонецЕсли;
    ВызватьИсключение "xml-case-bound";
КонецФункции
Процедура XFObserve(Знач N)
    Label = Прав("0" + Строка(N), 2);
    Попытка
        Value = XFCase(N);
    Исключение
        Сообщить("XF-" + Label + ": [action-error]");
        Возврат;
    КонецПопытки;
    Попытка
        Record = XFEncode(Value);
    Исключение
        Сообщить("XF-" + Label + ": [observer-error]");
        Возврат;
    КонецПопытки;
    Сообщить("XF-" + Label + ": [ok|" + Record + "]");
КонецПроцедуры
Сообщить("XF-C1: [" + XFEncode("") + "]");
Сообщить("XF-C2: [" + XFEncode("A ;""😀") + "]");
Для N = 1 По 33 Цикл XFObserve(N); КонецЦикла;
