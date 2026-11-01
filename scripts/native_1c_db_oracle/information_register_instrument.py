"""Closed InformationRegister wrappers reusing authenticated reviewed batch dispatch."""
import re
from catalog_read_instrument import once, wrap as base_wrap, SERVER, CLIENT
from information_register_fixture import BLOCKS, STATES, profile
from inject_metadata import bsl_string


def wrap(raw,name):
    if name.startswith('B'):
        source=raw.decode('utf-8-sig')
        # Resolve unavailable globals inside this same CRRun lexical scope.
        source=re.sub(r'(Try CREmit\("[0-9]{2}", )(.+?)(\); Except )',
            lambda m:m[1]+'Вычислить('+bsl_string(m[2])+')'+m[3],source)
        # Only source-owned fixed assignment targets, resolved inside CRRun.
        source=re.sub(r'\b(G1|G2|G3|GM|GV|S|F|FM|D) = ([^;\n]*InformationRegisters[^;\n]*);',
            lambda m:m[1]+' = Вычислить('+bsl_string(m[2])+');',source)
        raw=source.encode('utf-8')
    if name.startswith('S'):
        source=raw.decode('utf-8-sig')
        # Two setup blocks share a module. Keep helpers at module scope, unique,
        # and pass diagnostics explicitly; no global observer state.
        source=re.sub(r'\bRGCount\(',name+'RGCount(Diagnostic, ',source)
        source=source.replace('Q = New Query; Q.Text = "SELECT COUNT(*)',
            'Diagnostic.phase = "setup-query-build";\nQ = New Query; Q.Text = "SELECT COUNT(*)')
        source=source.replace('W = Q.Execute().Select(); W.Next(); Return W.N;',
            'Diagnostic.phase = "setup-query-execute";\nW = Q.Execute().Select();\nDiagnostic.phase = "setup-query-row";\nW.Next(); Return W.N;')
        raw=source.encode('utf-8')
    text=base_wrap(raw,name)
    # Packet's explicit Try/Except uses English Message; same bounded accumulator.
    text=text.replace('Message(', 'Lines.Добавить(')
    if name.startswith('S'):
        lines=[]
        for line in text.splitlines():
            phase=None
            match=re.match(r'Try '+name+r'CREmit\(Lines, "([0-9]{2})",',line)
            if match:phase='setup-witness-'+match[1]
            elif line.startswith('Q = New Query;'):phase='setup-query-execute'
            elif line.startswith(('CM = ', 'C = ', 'R = ', 'R.')):phase='setup-mutate'
            if phase:lines.append('Diagnostic.phase = "'+phase+'";')
            lines.append(line)
        text='\n'.join(lines)+'\n'
    return text


def instrument(raw,name,s,files,*,nonce,evidence):
    text=raw.decode('utf-8-sig').replace('\r\n','\n')
    if 'CBSelected' in text or 'CBDispatch' in text:raise ValueError('already-instrumented')
    blocks=''.join(wrap(files[block+'.bsl'],'B'+str(i)) for i,block in enumerate(BLOCKS))
    all_function='Функция CBAll()\nOutputs = Новый Структура;\n'
    for i,block in enumerate(BLOCKS):all_function+=f'Outputs.Вставить("{block}", B{i}CRRun());\n'
    all_function+='Возврат Outputs;\nКонецФункции\n'
    if name=='NativeOracleServer.bsl':
        p=profile(s)
        text=once(text,'Метаданные.Справочники.Количество() <> 1','Метаданные.Справочники.Количество() <> 2')
        text=once(text,'Метаданные.РегистрыСведений.Количество() <> 0','Метаданные.РегистрыСведений.Количество() <> 1')
        guard=f'''Каталог = Метаданные.Справочники.{p['catalog']};
    Если Каталог.ДлинаКода <> 2 Или Каталог.ДлинаНаименования <> 8 Или Каталог.Иерархический
        Или Каталог.Реквизиты.Количество() <> 0 Или Каталог.ТабличныеЧасти.Количество() <> 0 Тогда ВызватьИсключение "metadata_mismatch"; КонецЕсли;
    Регистр = Метаданные.РегистрыСведений.{p['register']};
    Если Регистр.Измерения.Количество() <> 2 Или Регистр.Ресурсы.Количество() <> 3
        Или Регистр.Реквизиты.Количество() <> 1 Тогда ВызватьИсключение "metadata_mismatch"; КонецЕсли;
    '''
        text=once(text,'    Каталог = Метаданные.Справочники.NativeOracleItems;','    '+guard+'Каталог = Метаданные.Справочники.NativeOracleItems;')
        dispatch=''
        for i,state in enumerate(STATES):
            blocks+=wrap(files['setup-'+state+'.bsl'],'S'+str(i))
            dispatch+=f'Если Control.operation = "information_register_setup_{state}" Тогда Output.Вставить("setup", S{i}CRRun(Response)); КонецЕсли;\n'
        server=SERVER.replace('catalog_read_','information_register_')
        old=',information_register_client,information_register_server,'+','.join('information_register_setup_'+n for n in ('empty','one','several','deleted','reused'))+','
        new=',information_register_client,information_register_server,'+','.join('information_register_setup_'+n for n in STATES)+','
        server=once(server,old,new)
        text+=server.replace('@@SETUP_DISPATCH@@',dispatch)
    elif name=='ManagedApplicationModule.bsl':
        text=once(text,'        Завершение = Новый Структура(','''        Если NativeOracleServer.CBSelected(ПараметрЗапуска) Тогда
            CBDispatch(ПараметрЗапуска);
            ЗавершитьРаботуСистемы(Ложь);
            Возврат;
        КонецЕсли;
        Завершение = Новый Структура(''')
        text+=CLIENT.replace('catalog_read_','information_register_')
    else:raise ValueError('module-name')
    text+=blocks+all_function
    for key,value in {'NONCE':nonce,'EVIDENCE':str(evidence),'SETUP_USER':'NativeOracleSetup','CRUD_USER':'NativeOracleCRUD'}.items():text=text.replace('@@'+key+'@@',bsl_string(value))
    if '@@' in text:raise ValueError('unexpanded')
    return text.encode('utf-8-sig')
