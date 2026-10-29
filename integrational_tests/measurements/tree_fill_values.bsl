// Bounded independent FillValues measurement. No expected native semantics.
Функция TreeFillExact(Знач Left, Знач Right)
    Если ТипЗнч(Left) <> Тип("Строка") Или ТипЗнч(Right) <> Тип("Строка") Тогда Возврат Ложь; КонецЕсли;
    Если СтрДлина(Left) <> СтрДлина(Right) Тогда Возврат Ложь; КонецЕсли;
    Для P = 1 По СтрДлина(Left) Цикл
        Если КодСимвола(Left, P) <> КодСимвола(Right, P) Тогда Возврат Ложь; КонецЕсли;
    КонецЦикла;
    Возврат Истина;
КонецФункции

Функция TreeFillPair(Знач First, Знач Second)
    Values = Новый Массив; Values.Add(First); Values.Add(Second); Возврат Values;
КонецФункции

Процедура TreeFillCount(Знач Collection, Знач Expected)
    N = Collection.Count();
    Если ТипЗнч(N) <> Тип("Число") Или N <> Expected Тогда ВызватьИсключение "tree-fill-count"; КонецЕсли;
КонецПроцедуры

Функция TreeFillCell(Знач Value, Знач Refs)
    Kind = ТипЗнч(Value);
    Если Kind = Тип("Неопределено") Тогда Возврат "U_"; КонецЕсли;
    Если Kind = Тип("Null") Тогда Возврат "L_"; КонецЕсли;
    Если Kind = Тип("Булево") Тогда Если Value Тогда Возврат "T_"; Иначе Возврат "F_"; КонецЕсли; КонецЕсли;
    Если Kind = Тип("Число") Тогда
        Если Value < 0 Или Value > 7 Или Цел(Value) <> Value Тогда ВызватьИсключение "tree-fill-number"; КонецЕсли;
        Возврат Сред("01234567", Value + 1, 1) + "_";
    КонецЕсли;
    Если Kind = Тип("Строка") Тогда
        Words = СтрРазделить("|hit|x|y|base|from-source|from-result|bad|new|1", "|", Истина);
        Для P = 0 По Words.Count() - 1 Цикл
            Если TreeFillExact(Value, Words[P]) Тогда Возврат Сред("abcdefghij", P + 1, 1) + "_"; КонецЕсли;
        КонецЦикла;
        ВызватьИсключение "tree-fill-string";
    КонецЕсли;
    Если Kind <> Тип("Структура") Тогда ВызватьИсключение "tree-fill-type"; КонецЕсли;
    TreeFillCount(Value, 1);
    Для Каждого Entry Из Value Цикл
        Если Не TreeFillExact(Entry.Key, "Mark") Тогда ВызватьИсключение "tree-fill-property"; КонецЕсли;
    КонецЦикла;
    Если TreeFillExact(Value.Mark, "base") Тогда Prefix = "P";
    ИначеЕсли TreeFillExact(Value.Mark, "from-source") Тогда Prefix = "Q";
    ИначеЕсли TreeFillExact(Value.Mark, "from-result") Тогда Prefix = "R";
    Иначе ВызватьИсключение "tree-fill-mark"; КонецЕсли;
    Index = -1;
    Для P = 0 По Refs.Count() - 1 Цикл
        Если Value = Refs[P] Тогда Index = P; Прервать; КонецЕсли;
    КонецЦикла;
    Если Index = -1 Тогда
        Если Refs.Count() >= 60 Тогда ВызватьИсключение "tree-fill-registry"; КонецЕсли;
        Index = Refs.Count(); Refs.Add(Value);
    КонецЕсли;
    Возврат Prefix + Сред("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwx", Index + 1, 1);
КонецФункции

Функция TreeFillCalibrate()
    Stage = "0";
    Попытка
        Stage = "1";
        X = Новый Структура("Mark", "base"); Y = Новый Структура("Mark", "base"); Alias = X;
        Stage = "2";
        Если X <> Alias Тогда ВызватьИсключение "tree-fill-structure-alias"; КонецЕсли;
        Stage = "3";
        Если X = Y Тогда ВызватьИсключение "tree-fill-structure-distinct"; КонецЕсли;
        Stage = "4";
        A = TreeFillPair(1, Истина); B = TreeFillPair(1, Истина); Alias = A;
        Stage = "5";
        Если A <> Alias Тогда ВызватьИсключение "tree-fill-array-alias"; КонецЕсли;
        Stage = "6";
        Если A = B Тогда ВызватьИсключение "tree-fill-array-distinct"; КонецЕсли;
        Stage = "7";
        F = Новый ФиксированныйМассив(A); G = Новый ФиксированныйМассив(A); Alias = F;
        Stage = "8";
        Если F <> Alias Тогда ВызватьИсключение "tree-fill-fixed-alias"; КонецЕсли;
        Stage = "9";
        Если F = G Тогда ВызватьИсключение "tree-fill-fixed-distinct"; КонецЕсли;
        Stage = "A";
        T = Новый ДеревоЗначений; Other = Новый ДеревоЗначений;
        Stage = "B";
        RootRows = T.Rows;
        Stage = "C";
        Cols = T.Columns;
        Stage = "D";
        R = T.Rows.Add();
        Stage = "E";
        OtherRow = T.Rows.Add();
        Stage = "F";
        ChildRows = R.Rows;
        Stage = "G";
        Expected = TreeFillPair(R, OtherRow); Empty = Новый Массив;
        TreeFillRows(RootRows, Expected, Неопределено); TreeFillRows(T.Rows, Expected, Неопределено);
        Stage = "H";
        Если T.Columns <> Cols Тогда ВызватьИсключение "tree-fill-columns-alias"; КонецЕсли;
        Stage = "I";
        TreeFillRows(ChildRows, Empty, R); TreeFillRows(R.Rows, Empty, R);
        Stage = "J";
        TreeFillRows(RootRows, Expected, Неопределено); TreeFillRows(Other.Rows, Empty, Неопределено);
        Stage = "K";
        Если Cols = Other.Columns Тогда ВызватьИсключение "tree-fill-columns-distinct"; КонецЕсли;
        Stage = "L";
        TreeFillRows(ChildRows, Empty, R); TreeFillRows(OtherRow.Rows, Empty, OtherRow);
        Stage = "M";
        Если R <> T.Rows.Get(0) Тогда ВызватьИсключение "tree-fill-row-alias"; КонецЕсли;
        Stage = "N";
        Если R = OtherRow Тогда ВызватьИсключение "tree-fill-row-distinct"; КонецЕсли;
        Stage = "O";
        Refs = Новый Массив;
        Stage = "P";
        Если Не TreeFillExact(TreeFillCell(1, Refs), "1_") Тогда ВызватьИсключение "tree-fill-number-calibration"; КонецЕсли;
        Stage = "Q";
        Если Не TreeFillExact(TreeFillCell(Истина, Refs), "T_") Тогда ВызватьИсключение "tree-fill-bool-calibration"; КонецЕсли;
        Stage = "R";
        Если Не TreeFillExact(TreeFillCell("1", Refs), "j_") Тогда ВызватьИсключение "tree-fill-string-calibration"; КонецЕсли;
    Исключение
        Возврат Stage;
    КонецПопытки;
    Возврат "-";
КонецФункции

Процедура TreeFillSchema(Знач Tree, Знач Columns, Знач Names, Знач Typed)
    TreeFillCount(Tree.Columns, Names.Count()); TreeFillCount(Columns, Names.Count());
    Для P = 0 По Names.Count() - 1 Цикл
        C = Tree.Columns.Get(P);
        Если C <> Columns[P] Или Не TreeFillExact(C.Name, Names[P]) Или Не TreeFillExact(C.Title, Names[P])
            Или ТипЗнч(C.Width) <> Тип("Число") Или C.Width <> 0 Тогда ВызватьИсключение "tree-fill-schema"; КонецЕсли;
        D = C.ValueType; Types = D.Types();
        Если Typed И P = 1 Тогда
            TreeFillCount(Types, 1); Если Types[0] <> Тип("Число") Тогда ВызватьИсключение "tree-fill-schema-type"; КонецЕсли;
        Иначе TreeFillCount(Types, 0); КонецЕсли;
        N = D.NumberQualifiers; Q = D.StringQualifiers; B = D.BinaryDataQualifiers;
        Если ТипЗнч(N.Digits) <> Тип("Число") Или N.Digits <> 0
            Или ТипЗнч(N.FractionDigits) <> Тип("Число") Или N.FractionDigits <> 0
            Или N.AllowedSign <> AllowedSign.Any
            Или ТипЗнч(Q.Length) <> Тип("Число") Или Q.Length <> 0 Или Q.AllowedLength <> AllowedLength.Variable
            Или D.DateQualifiers.DateFractions <> DateFractions.DateTime
            Или ТипЗнч(B.Length) <> Тип("Число") Или B.Length <> 0 Или B.AllowedLength <> AllowedLength.Variable Тогда
            ВызватьИсключение "tree-fill-qualifiers";
        КонецЕсли;
    КонецЦикла;
КонецПроцедуры

Процедура TreeFillRows(Знач Rows, Знач Expected, Знач Parent)
    Если ТипЗнч(Rows) <> Тип("КоллекцияСтрокДереваЗначений") Тогда ВызватьИсключение "tree-fill-rows-type"; КонецЕсли;
    TreeFillCount(Rows, Expected.Count());
    Если Rows.Parent <> Parent Тогда ВызватьИсключение "tree-fill-collection-parent"; КонецЕсли;
    Для P = 0 По Expected.Count() - 1 Цикл
        Если Rows.Get(P) <> Expected[P] Тогда ВызватьИсключение "tree-fill-row-order"; КонецЕсли;
    КонецЦикла;
КонецПроцедуры

Функция TreeFillSnapshot(Знач S, Знач Source, Знач Original, Знач Refs)
    Если S.Tree.Columns <> S.ColumnCollection
        Или S.Foreign.Columns <> S.ForeignColumnCollection Тогда
        ВызватьИсключение "tree-fill-retained-collection";
    КонецЕсли;
    TreeFillCount(S.RowCollections, S.Nodes.Count() + 1);
    TreeFillSchema(S.Tree, S.Columns, S.Names, S.Typed);
    TreeFillSchema(S.Foreign, S.ForeignColumns, S.ForeignNames, Ложь);
    Empty = Новый Массив; TreeFillRows(S.Foreign.Rows, Empty, Неопределено);
    TreeFillRows(S.ForeignRowCollection, Empty, Неопределено);
    Если S.Nodes.Count() = 0 Тогда
        TreeFillRows(S.Tree.Rows, Empty, Неопределено);
        TreeFillRows(S.RowCollections[0], Empty, Неопределено);
        Text = S.Mode + S.Mode + "................................................";
    Иначе
        TreeFillCount(S.Nodes, 6); TreeFillRows(S.Tree.Rows, TreeFillPair(S.Nodes[0], S.Nodes[1]), Неопределено);
        TreeFillRows(S.RowCollections[0], TreeFillPair(S.Nodes[0], S.Nodes[1]), Неопределено);
        Text = "BB";
        Для P = 0 По 5 Цикл
            R = S.Nodes[P];
            Parent = Неопределено; Children = Новый Массив;
            Если P = 0 Тогда Children = TreeFillPair(S.Nodes[3], S.Nodes[4]);
            ИначеЕсли P = 1 Тогда Children.Add(S.Nodes[2]);
            ИначеЕсли P = 2 Тогда Parent = S.Nodes[1];
            ИначеЕсли P = 3 Тогда Parent = S.Nodes[0]; Children.Add(S.Nodes[5]);
            ИначеЕсли P = 4 Тогда Parent = S.Nodes[0];
            ИначеЕсли P = 5 Тогда Parent = S.Nodes[3]; КонецЕсли;
            Если R.Owner() <> S.Tree Или R.Parent <> Parent Тогда ВызватьИсключение "tree-fill-row-links"; КонецЕсли;
            TreeFillRows(R.Rows, Children, R);
            TreeFillRows(S.RowCollections[P + 1], Children, R);
            Для C = 0 По 3 Цикл Text = Text + TreeFillCell(R.Get(C), Refs); КонецЦикла;
        КонецЦикла;
    КонецЕсли;
    Kind = ТипЗнч(Source); Container = Ложь;
    Если Kind = Тип("Массив") Тогда Tag = "A"; Container = Истина;
    ИначеЕсли Kind = Тип("ФиксированныйМассив") Тогда Tag = "F"; Container = Истина;
    ИначеЕсли Kind = Тип("Строка") Тогда Tag = "S";
    ИначеЕсли Kind = Тип("Число") Тогда Tag = "N";
    ИначеЕсли Kind = Тип("Булево") Тогда Tag = "B";
    ИначеЕсли Kind = Тип("Неопределено") Тогда Tag = "U";
    ИначеЕсли Kind = Тип("Null") Тогда Tag = "L";
    ИначеЕсли Kind = Тип("Структура") Тогда Tag = "R";
    Иначе ВызватьИсключение "tree-fill-source-type"; КонецЕсли;
    Identity = "0"; Values = Новый Массив;
    Если Container Тогда
        Count = Source.Count();
        Если ТипЗнч(Count) <> Тип("Число") Или Count < 0 Или Count > 3 Или Цел(Count) <> Count Тогда ВызватьИсключение "tree-fill-source-count"; КонецЕсли;
        Если ТипЗнч(Original) = Kind И Source = Original Тогда Identity = "1"; Иначе Identity = "2"; КонецЕсли;
        Для P = 0 По Count - 1 Цикл Values.Add(Source[P]); КонецЦикла;
    Иначе Count = 1; Values.Add(Source); КонецЕсли;
    Text = Text + Tag + Identity + Сред("0123", Count + 1, 1);
    Для P = 0 По 2 Цикл
        Если P < Count Тогда Text = Text + TreeFillCell(Values[P], Refs); Иначе Text = Text + ".."; КонецЕсли;
    КонецЦикла;
    Если СтрДлина(Text) <> 59 Тогда ВызватьИсключение "tree-fill-width"; КонецЕсли;
    Возврат Text;
КонецФункции

Функция TreeFillFresh(Знач Case)
    S = Новый Структура("Tree,Nodes,Columns,Names,Typed,Mode,Foreign,ForeignColumns,ForeignNames,ColumnCollection,RowCollections,ForeignColumnCollection,ForeignRowCollection");
    S.Tree = Новый ДеревоЗначений; S.Nodes = Новый Массив; S.Columns = Новый Массив;
    S.Names = СтрРазделить("Id|Key|Group|Mark", "|"); S.Typed = Case >= 41 И Case <= 44; S.Mode = "B";
    Если Case = 6 Тогда S.Names = Новый Массив; S.Mode = "N";
    ИначеЕсли Case = 5 Или Case = 19 Тогда S.Mode = "E"; КонецЕсли;
    Для P = 0 По S.Names.Count() - 1 Цикл
        Если S.Typed И P = 1 Тогда C = S.Tree.Columns.Add(S.Names[P], Новый ОписаниеТипов("Число"));
        Иначе C = S.Tree.Columns.Add(S.Names[P]); КонецЕсли;
        C.Title = S.Names[P]; C.Width = 0; S.Columns.Add(C);
    КонецЦикла;
    Если S.Mode = "B" Тогда
        A = S.Tree.Rows.Add(); B = S.Tree.Rows.Add(); B1 = B.Rows.Add(); A1 = A.Rows.Add(); A2 = A.Rows.Add(); A11 = A1.Rows.Add();
        S.Nodes.Add(A); S.Nodes.Add(B); S.Nodes.Add(B1); S.Nodes.Add(A1); S.Nodes.Add(A2); S.Nodes.Add(A11);
        Для P = 0 По 5 Цикл
            R = S.Nodes[P]; R.Id = P + 1; Если S.Typed Тогда R.Key = 0; Иначе R.Key = "hit"; КонецЕсли;
            Если P = 0 Или P = 2 Или P = 3 Тогда R.Group = "x"; Иначе R.Group = "y"; КонецЕсли; R.Mark = "base";
        КонецЦикла;
    КонецЕсли;
    S.Foreign = Новый ДеревоЗначений; C = S.Foreign.Columns.Add("Id"); C.Title = "Id"; C.Width = 0;
    S.ForeignColumns = Новый Массив; S.ForeignColumns.Add(C); S.ForeignNames = Новый Массив; S.ForeignNames.Add("Id");
    S.ColumnCollection = S.Tree.Columns; S.RowCollections = Новый Массив; S.RowCollections.Add(S.Tree.Rows);
    Для Каждого R Из S.Nodes Цикл S.RowCollections.Add(R.Rows); КонецЦикла;
    S.ForeignColumnCollection = S.Foreign.Columns; S.ForeignRowCollection = S.Foreign.Rows;
    Возврат S;
КонецФункции

Функция TreeFillBaseline(Знач Case)
    Если Case = 7 Тогда Text = "NN................................................";
    ИначеЕсли Case = 6 Тогда Text = "EE................................................";
    Иначе
        Text = "BB";
        Для P = 0 По 5 Цикл
            Text = Text + Сред("123456", P + 1, 1) + "_";
            Если Case = 29 Или Case = 30 Или Case = 32 Тогда Text = Text + "0_"; Иначе Text = Text + "b_"; КонецЕсли;
            Если P = 0 Или P = 2 Или P = 3 Тогда Text = Text + "c_"; Иначе Text = Text + "d_"; КонецЕсли;
            Text = Text + "e_";
        КонецЦикла;
    КонецЕсли;
    Tail = "N014_....";
    Если Case = 25 Тогда Tail = "S01i_....";
    ИначеЕсли Case = 26 Тогда Tail = "U01U_....";
    ИначеЕсли Case = 27 Тогда Tail = "L01L_....";
    ИначеЕсли Case = 28 Или Case = 32 Тогда Tail = "B01T_....";
    ИначеЕсли Case = 29 Тогда Tail = "S01j_....";
    ИначеЕсли Case = 30 Тогда Tail = "S01h_....";
    ИначеЕсли Case = 31 Тогда Tail = "R01P0...."; КонецЕсли;
    Возврат Text + Tail;
КонецФункции

Функция TreeFillProbe(Знач Case)
    Попытка
        Mode = 1;
        Если Case = 6 Тогда Mode = 5;
        ИначеЕсли Case = 7 Тогда Mode = 6;
        ИначеЕсли Case >= 29 И Case <= 30 Или Case = 32 Тогда Mode = 41; КонецЕсли;
        S = TreeFillFresh(Mode); Refs = Новый Массив;
        Value = 4;
        Если Case = 25 Тогда Value = "new";
        ИначеЕсли Case = 26 Тогда Value = Неопределено;
        ИначеЕсли Case = 27 Тогда Value = Null;
        ИначеЕсли Case = 28 Или Case = 32 Тогда Value = Истина;
        ИначеЕсли Case = 29 Тогда Value = "1";
        ИначеЕсли Case = 30 Тогда Value = "bad";
        ИначеЕсли Case = 31 Тогда Value = Новый Структура("Mark", "base"); КонецЕсли;
        Original = Value;
        Before = TreeFillSnapshot(S, Value, Original, Refs);
        Если Не TreeFillExact(Before, TreeFillBaseline(Case)) Тогда Возврат "B"; КонецЕсли;
    Исключение Возврат "P"; КонецПопытки;
    Outcome = "S";
    Попытка
        Если Case = 1 Или Case = 6 Или Case = 7 Тогда S.Tree.Rows.FillValues(Value);
        ИначеЕсли Case = 2 Тогда S.Tree.Rows.FillValues(Value, "Key");
        ИначеЕсли Case = 3 Тогда S.Nodes[0].Rows.FillValues(Value);
        ИначеЕсли Case = 4 Тогда S.Nodes[0].Rows.FillValues(Value, "Key");
        ИначеЕсли Case = 5 Тогда S.Nodes[3].Rows.FillValues(Value, "Key");
        ИначеЕсли Case = 8 Тогда S.Tree.Rows.FillValues(Value, "");
        ИначеЕсли Case = 9 Тогда S.Tree.Rows.FillValues(Value, " Key , Group ");
        ИначеЕсли Case = 10 Тогда S.Tree.Rows.FillValues(Value, "Missing");
        ИначеЕсли Case = 11 Тогда S.Tree.Rows.FillValues(Value, "Key,Missing");
        ИначеЕсли Case = 12 Тогда S.Tree.Rows.FillValues(Value, "Missing,Key");
        ИначеЕсли Case = 13 Тогда S.Tree.Rows.FillValues(Value, "Key,Group");
        ИначеЕсли Case = 14 Тогда S.Tree.Rows.FillValues(Value, "Key,Key");
        ИначеЕсли Case = 15 Тогда S.Tree.Rows.FillValues(Value, "Key,");
        ИначеЕсли Case = 16 Тогда S.Tree.Rows.FillValues(Value, 0);
        ИначеЕсли Case = 17 Тогда S.Tree.Rows.FillValues(Value, S.Columns[1]);
        ИначеЕсли Case = 18 Тогда S.Tree.Rows.FillValues(Value, S.ForeignColumns[0]);
        ИначеЕсли Case = 19 Тогда S.Tree.Rows.FillValues(Value, Неопределено);
        ИначеЕсли Case = 20 Тогда S.Tree.Rows.FillValues(Value, Новый Массив);
        ИначеЕсли Case = 21 Тогда S.Tree.Rows.FillValues();
        ИначеЕсли Case = 22 Тогда S.Tree.Rows.FillValues(Value, "Key", Истина);
        ИначеЕсли Case = 23 Тогда Result = S.Tree.Rows.FillValues(Value, "Key");
        ИначеЕсли Case = 24 Тогда S.Tree.Rows.зАпОлНиТьЗнАчЕнИя(Value, "kEy");
        Иначе S.Tree.Rows.FillValues(Value, "Key"); КонецЕсли;
    Исключение Outcome = "E"; КонецПопытки;
    Попытка After = TreeFillSnapshot(S, Value, Original, Refs);
    Исключение Возврат "Q"; КонецПопытки;
    Попытка
        Если Case = 31 Тогда Value.Mark = "from-source"; КонецЕсли;
        Shared = TreeFillSnapshot(S, Value, Original, Refs);
    Исключение Возврат "R"; КонецПопытки;
    Возврат Outcome + Before + After + Shared;
КонецФункции

Calibration = TreeFillCalibrate();
Сообщить("TF-C: [" + Calibration + "]");
Для Case = 1 По 32 Цикл
    Сообщить("TF-" + Строка(Case) + ": [" + TreeFillProbe(Case) + "]");
КонецЦикла;
