// Ordinary local-file family, only fresh uniquely named owned temporary directories.
// !todo Exotic encodings/streams, permission attributes and cross-platform wildcard corners.
Функция FIEncode(Знач Text)
    Если ТипЗнч(Text) <> Тип("Строка") Или СтрДлина(Text) > 56 Тогда
        ВызватьИсключение "file-observer-text-bound";
    КонецЕсли;
    Record = "S" + Строка(СтрДлина(Text)) + ":";
    Для P = 1 По СтрДлина(Text) Цикл
        Code = КодСимвола(Text, P);
        Если Code < 0 Или Code > 65535 Тогда ВызватьИсключение "file-observer-unit-bound"; КонецЕсли;
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
Функция FICase(Знач N, Знач Root, R, W)
    A = Root + "/a.txt"; B = Root + "/b.txt";
    Если N = 1 Тогда
        F = Новый File(A); Возврат F.Name + ":" + F.BaseName + ":" + F.Extension + ":" + Строка(F.FullName = A) + ":" + Строка(F.Path = Root + "/");
    ИначеЕсли N = 2 Тогда
        F = Новый Файл(Root); Возврат Строка(F.Существует()) + ":" + Строка(F.ЭтоКаталог()) + ":" + Строка(F.ЭтоФайл());
    ИначеЕсли N = 3 Тогда
        W.Open(A, "UTF-8"); W.Write("Привет"); W.Close(); Возврат Base64String(Новый BinaryData(A));
    ИначеЕсли N = 4 Тогда
        W.Open(A, "UTF-8"); W.WriteLine("a"); W.WriteLine(""); W.Write("b"); W.Close(); R.Open(A, "UTF-8"); Возврат R.ReadLine() + ":" + R.ReadLine() + ":" + R.ReadLine() + ":" + Строка(R.ReadLine() = Неопределено);
    ИначеЕсли N = 5 Тогда
        W.Open(A, "UTF-8"); W.Write("abcdef"); W.Close(); R.Open(A, "UTF-8"); Возврат R.Read(2) + ":" + R.Read(3) + ":" + R.Read() + ":" + Строка(R.Read() = Неопределено);
    ИначеЕсли N = 6 Тогда
        W.Open(A, "UTF-8"); W.Write("a"); W.Close(); W.Open(A, "UTF-8", , Истина); W.Write("b"); W.Close(); Возврат Base64String(Новый BinaryData(A));
    ИначеЕсли N = 7 Тогда
        W.Open(A, "UTF-8"); W.Write("abcdef"); W.Close(); W.Open(A, "UTF-8"); W.Write("x"); W.Close(); Возврат Base64String(Новый BinaryData(A));
    ИначеЕсли N = 8 Тогда
        W.Open(A, "windows-1251"); W.Write("Привет"); W.Close(); R.Open(A, "windows-1251"); Возврат R.Read() + ":" + Base64String(Новый BinaryData(A));
    ИначеЕсли N = 9 Тогда
        W.Open(A, TextEncoding.UTF16); W.Write("Яa"); W.Close(); R.Open(A); Возврат R.Read() + ":" + Base64String(Новый BinaryData(A));
    ИначеЕсли N = 10 Тогда
        W.Open(A); W.WriteLine("a"); W.Close(); R.Open(A); Возврат R.ReadLine() + ":" + Base64String(Новый BinaryData(A));
    ИначеЕсли N = 11 Тогда
        D = Base64Value("AAEC/w=="); Возврат Строка(D.Size()) + ":" + Base64String(D);
    ИначеЕсли N = 12 Тогда
        D = GetBinaryDataFromString("Привет"); Возврат GetStringFromBinaryData(D) + ":" + Base64String(D);
    ИначеЕсли N = 13 Тогда
        D = GetBinaryDataFromString("A", "UTF-8", Истина); Возврат Base64String(D) + ":" + GetStringFromBinaryData(D, "UTF-8");
    ИначеЕсли N = 14 Тогда
        D = Base64Value("AAEC/w=="); D.Write(A); F = Новый File(A); Возврат Строка(F.Size()) + ":" + Base64String(Новый BinaryData(A));
    ИначеЕсли N = 15 Тогда
        Base64Value("AQID").Write(A); CopyFile(A, B); F = Новый File(A); Возврат Base64String(Новый BinaryData(B)) + ":" + Строка(F.Exists());
    ИначеЕсли N = 16 Тогда
        Base64Value("AQID").Write(A); MoveFile(A, B); F = Новый File(A); Возврат Base64String(Новый BinaryData(B)) + ":" + Строка(F.Exists());
    ИначеЕсли N = 17 Тогда
        Base64Value("AQID").Write(A); Base64Value("AA==").Write(B); Found = FindFiles(Root, "*.txt"); Exact = FindFiles(A); Возврат Строка(Found.Count()) + ":" + Строка(Exact.Count()) + ":" + Exact[0].Name;
    ИначеЕсли N = 18 Тогда
        Base64Value("AQID").Write(A); DeleteFiles(A); F = Новый File(A); G = Новый File(Root); Возврат Строка(F.Exists()) + ":" + Строка(G.Exists());
    ИначеЕсли N = 19 Тогда
        Возврат Строка(ТипЗнч(W) = Тип("TextWriter")) + ":" + Строка(ТипЗнч(R) = Тип("TextReader")) + ":" + Строка(ТипЗнч(Новый File(A)) = Тип("File")) + ":" + Строка(ТипЗнч(Base64Value("")) = Тип("BinaryData"));
    ИначеЕсли N = 20 Тогда
        Возврат Строка(TextEncoding.UTF8 = КодировкаТекста.UTF8) + ":" + Строка(ТипЗнч(TextEncoding.UTF16) = Тип("TextEncoding"));
    ИначеЕсли N = 21 Тогда
        Base64Value("").Write(A); R.Open(A, "UTF-8"); Возврат Строка(R.Read() = Неопределено) + ":" + Строка(R.ReadLine() = Неопределено);
    ИначеЕсли N = 22 Тогда
        W.Open(A); W.Write("a"); W.Close(); W.Close(); R.Open(A); R.Close(); R.Close(); Возврат "closed";
    ИначеЕсли N = 23 Тогда
        Попытка R.Read(); Исключение Возврат "read-error"; КонецПопытки; Возврат "unexpected-success";
    ИначеЕсли N = 24 Тогда
        Попытка W.Write("a"); Исключение Возврат "write-error"; КонецПопытки; Возврат "unexpected-success";
    ИначеЕсли N = 25 Тогда
        Попытка R.Open(A); Исключение Возврат "missing-error"; КонецПопытки; Возврат "unexpected-success";
    ИначеЕсли N = 26 Тогда
        Попытка D = Новый BinaryData(A); Исключение Возврат "missing-error"; КонецПопытки; Возврат "unexpected-success";
    ИначеЕсли N = 27 Тогда
        W.Open(A, "UTF-8"); W.Close(); Возврат Base64String(Новый BinaryData(A));
    ИначеЕсли N = 28 Тогда
        W = Новый TextWriter(A, "UTF-8"); W.Write("a"); W.Close(); W.Open(B, "UTF-8"); W.Write("b"); W.Close(); Возврат Base64String(Новый BinaryData(A)) + ":" + Base64String(Новый BinaryData(B));
    ИначеЕсли N = 29 Тогда
        GetBinaryDataFromString("abc").Write(A); R = Новый TextReader(A, "UTF-8"); X = R.Read(1); R.Close(); R.Open(A, "UTF-8"); Возврат X + ":" + R.Read();
    ИначеЕсли N = 30 Тогда
        W.Open(A, "UTF-8", "|"); W.WriteLine("a"); W.WriteLine("b", ";"); W.Close(); R.Open(A, "UTF-8", "|"); Возврат R.ReadLine() + ":" + R.ReadLine(";");
    ИначеЕсли N = 31 Тогда
        GetBinaryDataFromString("a" + Символы.ВК + Символы.ПС + "b" + Символы.ПС).Write(A); R.Open(A, "UTF-8"); Возврат R.Read();
    ИначеЕсли N = 32 Тогда
        D = GetBinaryDataFromString("Я", "UTF-16BE", Истина); Возврат Base64String(D) + ":" + GetStringFromBinaryData(D, "UTF-16BE");
    ИначеЕсли N = 33 Тогда
        CreateDirectory(Root);
        Temp = TempFilesDir(); Other = GetTempFileName(".file-family");
        G = Новый File(Other);
        Возврат Строка(СтрДлина(Temp) > 0) + ":" + Строка(Other <> Root) + ":" + G.Extension + ":" + Строка(G.Exists());
    КонецЕсли;
    ВызватьИсключение "file-case-bound";
КонецФункции
Функция FIOwnedCase(Знач N)
    Root = GetTempFileName("file-family");
    F = Новый File(Root);
    Если F.Exists() Тогда ВызватьИсключение "file-fixture-collision"; КонецЕсли;
    R = Новый TextReader; W = Новый TextWriter;
    CreateDirectory(Root);
    Попытка
        Value = FICase(N, Root, R, W);
        R.Close(); W.Close();
        DeleteFiles(Root + "/a.txt"); DeleteFiles(Root + "/b.txt");
        Remaining = FindFiles(Root, "*");
        Если Remaining.Count() <> 0 Тогда ВызватьИсключение "file-fixture-not-empty"; КонецЕсли;
        DeleteFiles(Root);
        Если F.Exists() Тогда ВызватьИсключение "file-fixture-cleanup"; КонецЕсли;
    Исключение
        Попытка R.Close(); Исключение КонецПопытки;
        Попытка W.Close(); Исключение КонецПопытки;
        Попытка DeleteFiles(Root + "/a.txt"); Исключение КонецПопытки;
        Попытка DeleteFiles(Root + "/b.txt"); Исключение КонецПопытки;
        Попытка
            Remaining = FindFiles(Root, "*");
            Если Remaining.Count() = 0 Тогда DeleteFiles(Root); КонецЕсли;
        Исключение КонецПопытки;
        ВызватьИсключение;
    КонецПопытки;
    Возврат Value;
КонецФункции
Процедура FIObserve(Знач N)
    Label = Прав("0" + Строка(N), 2);
    Попытка
        Value = FIOwnedCase(N);
    Исключение
        Сообщить("FI-" + Label + ": [action-error]");
        Возврат;
    КонецПопытки;
    Попытка
        Record = FIEncode(Value);
    Исключение
        Сообщить("FI-" + Label + ": [observer-error]");
        Возврат;
    КонецПопытки;
    Сообщить("FI-" + Label + ": [ok|" + Record + "]");
КонецПроцедуры
Сообщить("FI-C1: [" + FIEncode("") + "]");
Сообщить("FI-C2: [" + FIEncode("A ;""😀") + "]");
Для N = 1 По 33 Цикл FIObserve(N); КонецЦикла;
