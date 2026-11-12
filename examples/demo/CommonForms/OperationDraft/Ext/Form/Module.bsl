&AtClient
Var PendingDraft;
&AtServer
Procedure Created(Cancel, StandardProcessing)
 DraftTitle = "Новая операция";
 Amount = 0;
 Comment = "";
 AppliedCount = 0;
 LastOutcome = "Изменения не подготовлены";
EndProcedure
&AtClient
Procedure EditDraft(Command)
 If PendingDraft <> Undefined Then
  DraftSnapshot = New Structure("DraftTitle,Amount,Comment", PendingDraft.DraftTitle, PendingDraft.Amount, PendingDraft.Comment);
 Else
  DraftSnapshot = New Structure("DraftTitle,Amount,Comment", DraftTitle, Amount, Comment);
 EndIf;
 OpenForm("CommonForm.DraftDetails", DraftSnapshot, ThisObject,
  Undefined, Undefined, Undefined, New CallbackDescription("DetailsCompleted", ThisObject));
EndProcedure
&AtClient
Procedure DetailsCompleted(Result, AdditionalParameters) Export
 If Result <> Undefined Then
  PendingDraft = Result;
  LastOutcome = "Черновик ожидает подтверждения";
 Else
  LastOutcome = "Редактирование отменено";
 EndIf;
EndProcedure
&AtClient
Procedure ConfirmDraft(Command)
 If PendingDraft = Undefined Then
  LastOutcome = "Нет подготовленных изменений";
 Else
  ShowQueryBox(New CallbackDescription("QuestionCompleted", ThisObject), "Применить подготовленные изменения?", QuestionDialogMode.YesNoCancel,
   Undefined, Undefined, "Подтверждение черновика");
 EndIf;
EndProcedure
&AtClient
Procedure QuestionCompleted(Result, AdditionalParameters) Export
 If Result = DialogReturnCode.Yes Then
  If PendingDraft <> Undefined Then
   DraftTitle = PendingDraft.DraftTitle;
   Amount = PendingDraft.Amount;
   Comment = PendingDraft.Comment;
   AppliedCount = AppliedCount + 1;
   PendingDraft = Undefined;
   LastOutcome = "Черновик применён";
  EndIf;
 ElsIf Result = DialogReturnCode.No Then
  PendingDraft = Undefined;
  LastOutcome = "Подготовленные изменения отклонены";
 Else
  LastOutcome = "Решение отложено";
 EndIf;
EndProcedure
&AtClient
Procedure ShowInfo(Command)
 ShowMessageBox(New CallbackDescription("InfoCompleted", ThisObject), "Это черновик в памяти формы. Документы и движения в базе не записываются.", Undefined, "Операция без записи");
EndProcedure
&AtClient
Procedure InfoCompleted(AdditionalParameters) Export
 LastOutcome = "Информация просмотрена";
EndProcedure
