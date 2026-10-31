// Standalone Columns.Clear lifetime observer; no native answers assumed.
Функция CCNum(Знач V)
    Если ТипЗнч(V) <> Тип("Число") Или V < 0 Или V > 9 Или Цел(V) <> V Тогда ВызватьИсключение "columns-clear-number"; КонецЕсли;
    Возврат Сред("0123456789", V + 1, 1);
КонецФункции
Функция CCSigned(Знач V)
    Если ТипЗнч(V) <> Тип("Число") Или V < -9 Или V > 9 Или Цел(V) <> V Тогда ВызватьИсключение "columns-clear-signed"; КонецЕсли;
    Если V < 0 Тогда Возврат Сред("abcdefghi", -V, 1); КонецЕсли;
    Возврат CCNum(V);
КонецФункции
Функция CCId(Знач V, Знач Registry)
    Если ТипЗнч(V) = Тип("Неопределено") Тогда Возврат "_"; КонецЕсли;
    Для I = 0 По Registry.Count() - 1 Цикл
        Candidate = Registry[I];
        Попытка Same = (V = Candidate);
        Исключение
            PrivateIdentityDescription = ОписаниеОшибки();
            ВызватьИсключение "columns-clear-identity-compare";
        КонецПопытки;
        Если Same Тогда Возврат Сред("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", I + 1, 1); КонецЕсли;
    КонецЦикла;
    Count = Registry.Count();
    Если Count >= 62 Тогда
        Если Count = 62 Тогда ВызватьИсключение "columns-clear-identities-count62"; КонецЕсли;
        ВызватьИсключение "columns-clear-identities-over62";
    КонецЕсли;
    Registry.Add(V); Возврат Сред("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", Registry.Count(), 1);
КонецФункции
Функция CCTypedId(Знач V, Знач Kind, Знач Optional, Знач Registry)
    K = ТипЗнч(V);
    Если K <> Kind И Не (Optional И K = Тип("Неопределено")) Тогда ВызватьИсключение "columns-clear-active-type"; КонецЕсли;
    Возврат CCId(V, Registry);
КонецФункции
Функция CCExact(Знач A, Знач B)
    Если ТипЗнч(A) <> Тип("Строка") Или ТипЗнч(B) <> Тип("Строка") Тогда Возврат Ложь; КонецЕсли;
    Если СтрДлина(A) <> СтрДлина(B) Тогда Возврат Ложь; КонецЕсли;
    Для P = 1 По СтрДлина(A) Цикл Если КодСимвола(A, P) <> КодСимвола(B, P) Тогда Возврат Ложь; КонецЕсли; КонецЦикла;
    Возврат Истина;
КонецФункции
Функция CCWord(Знач V)
    Если CCExact(V, "") Тогда Возврат "n"; КонецЕсли;
    Words = СтрРазделить("Key|Secondary|Tag|P|Q|X|Y|a|b|c|d|e|f", "|", Истина);
    Для I = 0 По Words.Count() - 1 Цикл
        Если CCExact(V, Words[I]) Тогда Возврат Сред("abcdefghijklm", I+1, 1); КонецЕсли;
    КонецЦикла;
    ВызватьИсключение "columns-clear-word";
КонецФункции
Функция CCFlag(Знач V) Если V Тогда Возврат "1"; Иначе Возврат "0"; КонецЕсли; КонецФункции
Функция CCCount(Знач V)
    Если ТипЗнч(V) <> Тип("Число") Или V < 0 Или V > 5 Или Цел(V) <> V Тогда ВызватьИсключение "columns-clear-count"; КонецЕсли;
    Возврат Сред("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", V + 1, 1);
КонецФункции
Функция CCCell(Знач V, Знач Registry)
    K = ТипЗнч(V);
    Если K = Тип("Неопределено") Тогда Возврат "U_"; КонецЕсли;
    Если K = Тип("Null") Тогда Возврат "L_"; КонецЕсли;
    Если K = Тип("Булево") Тогда Возврат "B" + CCFlag(V); КонецЕсли;
    Если K = Тип("Число") Тогда Возврат "N" + CCSigned(V); КонецЕсли;
    Если K = Тип("Строка") И СтрДлина(V) = 1 Тогда
        Для I = 1 По 18 Цикл
            Если CCExact(V, Сред("abcdefghijklmnopqr", I, 1)) Тогда Возврат "S" + V; КонецЕсли;
        КонецЦикла;
    КонецЕсли;
    ВызватьИсключение "columns-clear-cell";
КонецФункции
// Access exceptions and unsupported observer values are deliberately separate.
Функция CCRead(Знач Ref, Знач Query)
    Result = Новый Массив;
    Попытка
        Если ТипЗнч(Ref) = Тип("Неопределено") Тогда Result.Add("A"); Result.Add(Неопределено); Возврат Result; КонецЕсли;
        Если Query = "id" Тогда V = Ref;
        ИначеЕсли Query = "owner" Тогда V = Ref.Owner();
        ИначеЕсли Query = "parent" Тогда V = Ref.Parent;
        ИначеЕсли Query = "level" Тогда V = Ref.Level();
        ИначеЕсли Query = "cell" Тогда V = Ref.Get(0);
        ИначеЕсли Query = "named" Тогда V = Ref.Key;
        ИначеЕсли Query = "children" Тогда V = Ref.Rows.Count();
        ИначеЕсли Query = "name" Тогда V = Ref.Name;
        ИначеЕсли Query = "title" Тогда V = Ref.Title;
        ИначеЕсли Query = "width" Тогда V = Ref.Width;
        ИначеЕсли Query = "count" Тогда V = Ref.Count();
        ИначеЕсли Query = "first" Тогда V = Ref.Get(0);
        Иначе ВызватьИсключение "columns-clear-query";
        КонецЕсли;
    Исключение
        OriginalQueryErrorDescription = ОписаниеОшибки();
        Result.Add("E"); Result.Add(Неопределено); Возврат Result;
    КонецПопытки;
    Result.Add("V"); Result.Add(V); Возврат Result;
КонецФункции
Функция CCQuery(Знач Ref, Знач Query, Знач Kind, Знач Registry)
    Value = CCRead(Ref, Query);
    Если Value[0] <> "V" Тогда Возврат Value[0] + "_"; КонецЕсли;
    V = Value[1];
    Если Kind = "I" Тогда
        // Type validation precedes identity comparison: an arbitrary object
        // must not acquire a tree/row/column label merely from query position.
        ValueKind = ТипЗнч(V); ValidKind = Ложь;
        Если Query = "id" Тогда
            RefKind = ТипЗнч(Ref);
            ValidKind = ValueKind = RefKind И (RefKind = Тип("СтрокаДереваЗначений") Или RefKind = Тип("КолонкаДереваЗначений"));
        ИначеЕсли Query = "owner" Тогда ValidKind = ValueKind = Тип("ДеревоЗначений") Или ValueKind = Тип("Неопределено");
        ИначеЕсли Query = "parent" Тогда ValidKind = ValueKind = Тип("СтрокаДереваЗначений") Или ValueKind = Тип("Неопределено");
        ИначеЕсли Query = "first" Тогда ValidKind = ValueKind = Тип("КолонкаДереваЗначений");
        КонецЕсли;
        Если Не ValidKind Тогда ВызватьИсключение "columns-clear-identity-query-type"; КонецЕсли;
        Попытка EncodedIdentity = CCId(V, Registry);
        Исключение
            OriginalIdentityQueryErrorDescription = ОписаниеОшибки();
            Если Найти(OriginalIdentityQueryErrorDescription, "columns-clear-identity-compare") > 0 Тогда Возврат "E_"; КонецЕсли;
            ВызватьИсключение "columns-clear-identity-query-domain";
        КонецПопытки;
        Возврат "I" + EncodedIdentity;
    КонецЕсли;
    Если Kind = "W" Тогда Возврат "W" + CCWord(V); КонецЕсли;
    Если Kind = "N" Тогда Возврат "N" + CCSigned(V); КонецЕсли;
    Возврат CCCell(V, Registry);
КонецФункции
Процедура CCFlatten(Знач Rows, Знач Nodes)
    Для Каждого R Из Rows Цикл
        Если ТипЗнч(R) <> Тип("СтрокаДереваЗначений") Тогда ВызватьИсключение "columns-clear-row-type"; КонецЕсли;
        Если Nodes.Count() >= 5 Тогда ВызватьИсключение "columns-clear-rows"; КонецЕсли;
        Nodes.Add(R); CCFlatten(R.Rows, Nodes);
    КонецЦикла;
КонецПроцедуры
Функция CCSnapshot(Знач T, Знач Refs, Знач Registry)
    Если ТипЗнч(T) <> Тип("ДеревоЗначений") Тогда ВызватьИсключение "columns-clear-tree-type"; КонецЕсли;
    Count = T.Columns.Count();
    Если Count > 3 Тогда ВызватьИсключение "columns-clear-columns"; КонецЕсли;
    Out = CCId(T, Registry) + CCNum(Count);
        Для Каждого C Из T.Columns Цикл
            Если ТипЗнч(C) <> Тип("КолонкаДереваЗначений") Тогда ВызватьИсключение "columns-clear-column-type"; КонецЕсли;
            Point = "08"; D = C.ValueType;
            Point = "09"; Types = D.Types(); Kind = "U";
            Point = "10";
            Если Types.Count() = 1 Тогда
                Если Types[0] = Тип("Число") Тогда Kind = "N";
                ИначеЕсли Types[0] = Тип("Строка") Тогда Kind = "S";
                Иначе ВызватьИсключение "columns-clear-column-type"; КонецЕсли;
            ИначеЕсли Types.Count() <> 0 Тогда ВызватьИсключение "columns-clear-types"; КонецЕсли;
            DateKind = "0"; Point = "11";
            Если D.DateQualifiers.DateFractions = DateFractions.Date Тогда DateKind = "1";
            ИначеЕсли D.DateQualifiers.DateFractions = DateFractions.Time Тогда DateKind = "2";
            ИначеЕсли D.DateQualifiers.DateFractions <> DateFractions.DateTime Тогда ВызватьИсключение "columns-clear-date"; КонецЕсли;
            Point = "12"; Out = Out + CCId(C, Registry);
            Point = "13"; Out = Out + CCWord(C.Name);
            Point = "14"; Out = Out + CCWord(C.Title);
            Point = "15"; Out = Out + CCNum(C.Width) + Kind;
            Point = "16"; Out = Out + CCNum(D.NumberQualifiers.Digits);
            Point = "17"; Out = Out + CCNum(D.NumberQualifiers.FractionDigits);
            Point = "18"; Out = Out + CCFlag(D.NumberQualifiers.AllowedSign = AllowedSign.Nonnegative);
            Point = "19"; Out = Out + CCNum(D.StringQualifiers.Length);
            Point = "20"; Out = Out + CCFlag(D.StringQualifiers.AllowedLength = AllowedLength.Fixed) + DateKind;
            Point = "21"; Out = Out + CCNum(D.BinaryDataQualifiers.Length);
            Point = "22"; Out = Out + CCFlag(D.BinaryDataQualifiers.AllowedLength = AllowedLength.Fixed);
            Point = "07";
        КонецЦикла;
    Nodes = Новый Массив; CCFlatten(T.Rows, Nodes);
    Out = Out + CCNum(Nodes.Count());
    Для Каждого R Из Nodes Цикл
        Out = Out + CCId(R, Registry) + CCTypedId(R.Parent, Тип("СтрокаДереваЗначений"), Истина, Registry) + CCTypedId(R.Owner(), Тип("ДеревоЗначений"), Истина, Registry);
        Out = Out + CCSigned(R.Level()) + CCNum(R.Rows.Count());
        Для I = 0 По Count - 1 Цикл Out = Out + CCCell(R.Get(I), Registry); КонецЦикла;
        Для Каждого C Из T.Columns Цикл Out = Out + CCCell(R[C.Name], Registry); КонецЦикла;
    КонецЦикла;
    Для I = 0 По 1 Цикл
        R = Refs[I];
        Out = Out + CCQuery(R,"id","I",Registry) + CCQuery(R,"owner","I",Registry);
        Out = Out + CCQuery(R,"parent","I",Registry) + CCQuery(R,"level","N",Registry);
        Out = Out + CCQuery(R,"cell","C",Registry) + CCQuery(R,"named","C",Registry);
        Out = Out + CCQuery(R,"children","N",Registry);
    КонецЦикла;
    C = Refs[2];
    Out = Out + CCQuery(C,"id","I",Registry) + CCQuery(C,"name","W",Registry);
    Out = Out + CCQuery(C,"title","W",Registry) + CCQuery(C,"width","N",Registry);
    Out = Out + CCQuery(Refs[3],"count","N",Registry) + CCQuery(Refs[3],"first","I",Registry);
    // Collection handles are identified structurally by their fixture owner,
    // never by equality of ephemeral Rows wrappers.
    Для I = 4 По 5 Цикл
        Out = Out + CCQuery(Refs[I],"count","N",Registry) + CCQuery(Refs[I],"parent","I",Registry);
    КонецЦикла;
    Возврат Out;
КонецФункции
Функция CCFixture(Знач Case, Знач Refs)
    T = Новый ДеревоЗначений; R = Неопределено; Child = Неопределено; C = Неопределено;
    Если Case <> 3 Тогда
        C = T.Columns.Add("Key");
        Если Case <> 5 Тогда T.Columns.Add("Secondary"); КонецЕсли;
        Если Case <> 4 Тогда
            R = T.Rows.Add(); R.Key = 1;
            Child = R.Rows.Add(); Child.Key = 2;
            Other = T.Rows.Add(); Other.Key = 3;
        КонецЕсли;
    КонецЕсли;
    Refs.Add(R); Refs.Add(Child); Refs.Add(C); Refs.Add(T.Columns); Refs.Add(T.Rows);
    Если Child = Неопределено Тогда Refs.Add(Неопределено); Иначе Refs.Add(Child.Rows); КонецЕсли;
    Возврат T;
КонецФункции
Функция CCError(Знач Description)
    Если Найти(Description,"Метод объекта не обнаружен") > 0 Или Найти(Description,"Метод не найден") > 0 Тогда Возврат "M"; КонецЕсли;
    Если Найти(Description,"Слишком много фактических параметров") > 0 Или Найти(Description,"Неверное количество параметров") > 0 Тогда Возврат "A"; КонецЕсли;
    Возврат "O";
КонецФункции
// DS6: named-selector statement/expression compatibility; no presumed outcomes.
Функция DSFixture(Знач Refs)
    T = Новый ДеревоЗначений;
    C = T.Columns.Add("Key"); C.Title = "P"; C.Width = 9;
    T.Columns.Add("Secondary");
    R = T.Rows.Add(); R.Key = 1;
    Child = R.Rows.Add(); Child.Key = 2;
    Other = T.Rows.Add(); Other.Key = 3;
    Refs.Add(R); Refs.Add(Child); Refs.Add(C); Refs.Add(T.Columns); Refs.Add(T.Rows); Refs.Add(Child.Rows);
    Возврат T;
КонецФункции
Функция DSProbe(Знач Case)
    Stage = "B";
    Попытка
        Refs = Новый Массив; Registry = Новый Массив; T = DSFixture(Refs); C = Refs[2];
        Before = CCSnapshot(T, Refs, Registry); Stage = "O"; Status = "S"; Expression = "--";
        Попытка
            Если Case = 1 Тогда T.Columns.Delete(0);
            ИначеЕсли Case = 2 Тогда T.Columns.Удалить(C);
            ИначеЕсли Case = 3 Тогда T.Columns.Delete("Key");
            ИначеЕсли Case = 4 Тогда T.Columns.Удалить("Key");
            ИначеЕсли Case = 5 Тогда Result = T.Columns.Delete("Key");
            Иначе Result = T.Columns.Удалить("Key");
            КонецЕсли;
        Исключение
            OriginalErrorDescription = ОписаниеОшибки();
            Status = CCError(OriginalErrorDescription);
        КонецПопытки;
        Если Case >= 5 И Status = "S" Тогда Expression = CCCell(Result, Registry); КонецЕсли;
        After = CCSnapshot(T, Refs, Registry);
        Возврат Status + "-0" + Expression + "/" + Before + "/" + After;
    Исключение
        OriginalObserverErrorDescription = ОписаниеОшибки();
        Возврат "X" + Stage;
    КонецПопытки;
КонецФункции
Функция CCCalibrate()
    Попытка
        Refs = Новый Массив; T = CCFixture(1, Refs); OtherRefs = Новый Массив; U = CCFixture(1, OtherRefs);
        Если T = U Или T <> T Тогда Возврат "I"; КонецЕсли;
        Если Refs[0] <> T.Rows.Get(0) Или Refs[1] <> Refs[0].Rows.Get(0) Тогда Возврат "I"; КонецЕсли;
        Если Refs[2] <> T.Columns.Get(0) Или Refs[2] = T.Columns.Get(1) Тогда Возврат "I"; КонецЕсли;
        Registry = Новый Массив; Before = CCSnapshot(T, Refs, Registry); After = CCSnapshot(T, Refs, Registry);
        Если Не CCExact(Before, After) Тогда Возврат "I"; КонецЕсли;
    Исключение
        OriginalCalibrationErrorDescription = ОписаниеОшибки();
        Возврат "E";
    КонецПопытки;
    Возврат "-";
КонецФункции
Сообщить("DS-C1: [" + CCCalibrate() + "]");
Для Case = 1 По 6 Цикл Сообщить("DS-" + Строка(Case) + ": [" + DSProbe(Case) + "]"); КонецЦикла;
