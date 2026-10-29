"""Closed tree-v1 native measurement; never the ordinary six-output contract."""
import base64
import json
import re
import full_suite as full
PROFILE = 'tree-v1'
WIRE_SCHEMA = 'native-1c-tree-v1'
STAGE_SCHEMA = 'native-1c-tree-stage-v1'
SOURCE = 'integrational_tests/measurements/tree_fill_values.bsl'
TARGET = 'scenarios/tree_fill_values.bsl'
CASE = 'tree_fill_values'
SOURCE_SHA256 = '47ee0383ac5a9db0bf9d4132b78f0ca40eb46712b4152654feec776ce38e22df'
COUNT = 33
MAX_OUTPUT = 8192
MAX_TRANSPORT = 65536
INPUT_FILES = {
    **{k:v for k,v in full.INPUT_FILES.items() if not k.startswith('integrational_tests/tests/')},
    full.CLIENT_SOURCE: full.CLIENT_TARGET,
    'scripts/native_1c_bootstrap/tree_suite.py': 'bootstrap/tree_suite.py',
    'scripts/native_1c_tree_fill_contract.py': 'bootstrap/native_1c_tree_fill_contract.py',
    SOURCE: TARGET,
}


def empty_report(nonce):
    if not full.valid_nonce(nonce): raise full.FullError('invalid_input')
    return {'schema':STAGE_SCHEMA,'profile':PROFILE,'nonce':nonce,'status':'not_started',
        'failure_kind':'prerequisites_failed','failed_case':None,'input_sha256':{},
        'observation_diagnostic':None,
        'cases':[{'name':CASE,'status':'not_started','source_sha256':None,'module_sha256':None,
                  'output_sha256':None,'output_size':None,'message_count':None}],
        'client_tree':full.empty_dates_report()}


def input_hashes(inputs):
    return {k:full.digest(full.secure_bytes(inputs/v, full.MAX_OUTPUT)) for k,v in INPUT_FILES.items()}


DIAGNOSTIC_CATEGORIES = frozenset(('invalid_type','output_limit','encoding','record_count',
    'calibration','record_shape','probe_b','probe_p','probe_q','probe_r','payload_contract'))
CALIBRATION_CODES = '0123456789ABCDEFGHIJKLMNOPQR'


class ObservationFailure(full.FullError):
    def __init__(self, diagnostic):
        super().__init__('unsupported_observation')
        self.diagnostic = diagnostic


def observation_diagnostic(raw, site):
    from native_1c_tree_fill_contract import validate_payload, ObservationError
    if site not in ('server','client'): raise full.FullError('invalid_input')
    def result(category, case=None, calibration=None):
        return {'site':site,'case':case,'category':category,'calibration':calibration}
    if type(raw) is not bytes: return result('invalid_type')
    if len(raw)>MAX_OUTPUT: return result('output_limit')
    if any(value<32 and value!=10 or value>126 for value in raw): return result('encoding')
    lines=raw.splitlines(keepends=True)
    if len(lines)!=COUNT: return result('record_count')
    if lines[0]!=b'TF-C: [-]\n':
        match=re.fullmatch(rb'TF-C: \[([0-9A-R])\]\n',lines[0])
        return result('calibration',0,match[1].decode() if match else None)
    for case,line in enumerate(lines[1:],1):
        prefix=f'TF-{case}: ['.encode()
        if not line.startswith(prefix) or not line.endswith(b']\n'):
            return result('record_shape',case)
        value=line[len(prefix):-2]
        if value in (b'B',b'P',b'Q',b'R'): return result('probe_'+value.decode().lower(),case)
        try: validate_payload(value,case)
        except ObservationError: return result('payload_contract',case)
    return None


def validate_diagnostic(value):
    if value is None: return
    if (type(value) is not dict or set(value)!={'site','case','category','calibration'}
            or type(value['site']) is not str or value['site'] not in ('server','client')
            or type(value['category']) is not str or value['category'] not in DIAGNOSTIC_CATEGORIES
            or (value['case'] is not None and (type(value['case']) is not int or not 0<=value['case']<=32))
            or (value['calibration'] is not None and (type(value['calibration']) is not str
                or len(value['calibration'])!=1 or value['calibration'] not in CALIBRATION_CODES))):
        raise full.FullError('invalid_result')
    category=value['category']
    if ((category=='calibration' and value['case']!=0)
            or (category in ('record_shape','probe_b','probe_p','probe_q','probe_r','payload_contract')
                and (type(value['case']) is not int or not 1<=value['case']<=32))
            or (category in ('invalid_type','output_limit','encoding','record_count') and value['case'] is not None)
            or (category!='calibration' and value['calibration'] is not None)):
        raise full.FullError('invalid_result')


def validate_observations(raw, site='server'):
    from native_1c_tree_fill_contract import validate_output, ObservationError
    try: return validate_output(raw)
    except ObservationError:
        diagnostic=observation_diagnostic(raw,site)
        if diagnostic is None: diagnostic={'site':site,'case':None,'category':'record_count','calibration':None}
        validate_diagnostic(diagnostic)
        raise ObservationFailure(diagnostic) from None


def client_module(source, template):
    if (type(source) is not bytes or full.digest(source) != SOURCE_SHA256
            or full.digest(template) != full.PREPROCESSOR_SOURCE_SHA256):
        raise full.FullError('invalid_input')
    original = source.decode('utf-8')
    marker = '\nCalibration = TreeFillCalibrate();\n'
    if ('\r' in original or 'TreeLane' in original or original.count(marker)!=1
            or original.count('Сообщить(')!=2): raise full.FullError('invalid_input')
    split=original.index(marker)+1
    declarations=re.sub(r'(?m)^(Функция |Процедура )',r'&НаКлиенте\n\1',original[:split])
    body=original[split:].replace('Сообщить(', 'TreeLaneCapture(')
    inverse=re.sub(r'(?m)^&НаКлиенте\n(?=Функция |Процедура )','',declarations)
    inverse+=body.replace('TreeLaneCapture(', 'Сообщить(')
    if inverse!=original: raise full.FullError('invalid_input')
    harness=full.client_parity_template(template).decode('utf-8')
    # The historical template inverse restores a legacy default writer. This
    # profile explicitly restores the already-used no-linebreak writer options.
    old_writer = '    Запись = Новый ЗаписьJSON;\n    Запись.ОткрытьФайл(Путь);\n'
    new_writer = ('    Перем ПараметрыJSON, Запись;\n'
        '    ПараметрыJSON = Новый ПараметрыЗаписиJSON(ПереносСтрокJSON.Нет, " ", Истина);\n'
        '    Запись = Новый ЗаписьJSON;\n    Запись.ОткрытьФайл(Путь, , , ПараметрыJSON);\n')
    if harness.count(old_writer) != 1 or new_writer in harness:
        raise full.FullError('invalid_input')
    rewritten = harness.replace(old_writer, new_writer, 1)
    if rewritten.replace(new_writer, old_writer, 1) != harness:
        raise full.FullError('invalid_input')
    harness = rewritten
    wire='        1, Номер, Фаза, Контекст, Значения));'
    if harness.count(wire)!=1: raise full.FullError('invalid_input')
    harness=harness.replace(wire,'        "tree-v1", Номер, Фаза, Контекст, Значения));')
    fixed=re.search(r'&НаКлиенте\nФункция ВычислитьПробу\(\)\n.*?\nКонецФункции\n',harness,re.DOTALL)
    if fixed is None or harness.count('Функция ВычислитьПробу()')!=1: raise full.FullError('invalid_input')
    # The exact finite ASCII alphabet is enforced before storage, not inferred from source comments.
    # Hence each character costs exactly one UTF-8 byte; LF is reserved per message.
    wrapper=f'''&НаКлиенте
Процедура TreeLaneCapture(Знач Text)
    Если ТипЗнч(Text) <> Тип("Строка") Тогда ВызватьИсключение "tree-type"; КонецЕсли;
    Для P = 1 По СтрДлина(Text) Цикл
        Code = КодСимвола(Text, P);
        Allowed = (Code >= 48 И Code <= 57) Или (Code >= 65 И Code <= 90)
            Или (Code >= 97 И Code <= 122) Или Code = 32 Или Code = 45 Или Code = 46
            Или Code = 58 Или Code = 91 Или Code = 93 Или Code = 95;
        Если Не Allowed Тогда ВызватьИсключение "tree-alphabet"; КонецЕсли;
    КонецЦикла;
    Если TreeLaneMessages.Count() >= {COUNT} Или TreeLaneCharacters + СтрДлина(Text) > {MAX_OUTPUT-COUNT} Тогда
        ВызватьИсключение "tree-limit";
    КонецЕсли;
    TreeLaneCharacters = TreeLaneCharacters + СтрДлина(Text);
    TreeLaneMessages.Add(Text);
КонецПроцедуры
'''+declarations+'&НаКлиенте\nПроцедура TreeLaneRun()\n'+body+'КонецПроцедуры\n'
    wrapper+='''&НаКлиенте
Функция ВычислитьПробу()
    TreeLaneMessages = Новый Массив;
    TreeLaneCharacters = 0;
    TreeLaneRun();
    Возврат TreeLaneMessages;
КонецФункции
'''
    prefix='&НаКлиенте\nПерем TreeLaneMessages;\n&НаКлиенте\nПерем TreeLaneCharacters;\n'
    return full.generated_module((prefix+harness[:fixed.start()]+wrapper+harness[fixed.end():]).encode('utf-8'))


def client_marker(path, nonce, phase):
    if not full.valid_nonce(nonce) or phase not in ('entered','completed'): raise full.FullError('invalid_input')
    value=full.strict_json(full.secure_bytes(path,16384),max_depth=3)
    if (type(value) is not dict or set(value)!={'schema','nonce','phase','witness','values'}
            or value['schema']!=PROFILE or value['nonce']!=nonce or value['phase']!=phase
            or value['witness']!='client' or type(value['values']) is not list
            or len(value['values'])!=(0 if phase=='entered' else COUNT)
            or any(type(v) is not str for v in value['values'])): raise full.FullError('invalid_result')
    if phase=='completed': validate_observations(full.serialize_messages(value['values']), 'client')
    return value


def run_suite(launcher, platform, launcher_epf, root, inputs, nonce):
    report=empty_report(nonce)
    report.update(status='failed',failure_kind='unexpected_failure')
    case=report['cases'][0]
    old=launcher.read_result,launcher.run_process,launcher.build_epf
    try:
        if platform.timeout!=120 or platform.user!='NativeSmoke' or platform.password is not None:
            raise full.FullError('invalid_input')
        report['input_sha256']=input_hashes(inputs)
        if report['input_sha256'][SOURCE]!=SOURCE_SHA256: raise full.FullError('invalid_input')
        full.absent(root); root.mkdir(mode=0o700)
        report['failed_case']=CASE; case['status']='failed'
        raw=full.secure_bytes(inputs/TARGET,full.MAX_OUTPUT)
        if full.digest(raw)!=SOURCE_SHA256: raise full.FullError('invalid_input')
        case['source_sha256']=SOURCE_SHA256
        expected=full.generated_module(raw)
        directory,output=root/(CASE+'-case'),root/(CASE+'.out')
        def process(command,cwd,log,timeout):
            if len(command)>1 and command[1]=='ENTERPRISE':
                if cwd!=directory: raise full.FullError('invalid_input')
                full.validate_case_request(command,directory,False)
            full.run_process(command,cwd,log,timeout)
        def build(platform_argument,source_xml,destination):
            if full.secure_bytes(source_xml.parent/'TestModule/Ext/ObjectModule.bsl',full.MAX_OUTPUT+3)!=expected:
                raise full.FullError('module_mismatch')
            old[2](platform_argument,source_xml,destination)
        launcher.read_result,launcher.run_process,launcher.build_epf=full.read_native_result,process,build
        full.absent(directory,output,root/(CASE+'.err'),output.with_suffix('.out.tmp'))
        launcher.run_case(platform,inputs/TARGET,launcher_epf,directory,output)
        full.require_zero_result(directory/'TestModule.build-result.txt',0)
        full.require_epf(directory/'TestModule.epf')
        if full.secure_bytes(directory/'src/TestModule/Ext/ObjectModule.bsl',full.MAX_OUTPUT+3)!=expected:
            raise full.FullError('module_mismatch')
        messages,_=full.read_native_result(directory/'result.json')
        actual=full.secure_bytes(output,MAX_OUTPUT)
        if len(messages)!=COUNT or actual!=full.serialize_messages(messages): raise full.FullError('output_mismatch')
        validate_observations(actual)
        full.absent(root/(CASE+'.err'),directory/'result.err')
        case.update(status='ok',module_sha256=full.digest(expected),output_sha256=full.digest(actual),output_size=len(actual),message_count=COUNT)
        report['failed_case']=None
        report['client_tree']=full.run_client_probe(platform,root/'client-tree',inputs,nonce,report['input_sha256'],tree_output=output)
        report['observation_diagnostic']=report['client_tree'].pop('observation_diagnostic',None)
        if report['client_tree']['status']!='ok': raise full.FullError(report['client_tree']['failure_kind'])
        if input_hashes(inputs)!=report['input_sha256']: raise full.FullError('invalid_input')
        report.update(status='ok',failure_kind='none')
    except Exception as error:
        if isinstance(error,ObservationFailure): report['observation_diagnostic']=error.diagnostic
        report['failure_kind']=error.kind if isinstance(error,full.FullError) else 'unexpected_failure'
    finally:
        launcher.read_result,launcher.run_process,launcher.build_epf=old
    return report


def write_report(path,report):
    raw=json.dumps(report,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if len(raw)>full.MAX_STAGE_REPORT: raise full.FullError('export_failed')
    with path.open('xb') as stream: stream.write(raw)


def finish_report(report,nonce,root,*,quiet,bus_cleanup_failed):
    suite=empty_report(nonce)
    try:
        path=root.parent/'stage3-report.json'
        if path.exists() or path.is_symlink(): suite=full.strict_json(full.secure_bytes(path,full.MAX_STAGE_REPORT))
        if (type(suite) is not dict or suite.get('schema')!=STAGE_SCHEMA
                or suite.get('profile')!=PROFILE or suite.get('nonce')!=nonce): raise full.FullError('invalid_result')
        if not quiet or bus_cleanup_failed: raise full.FullError('process_failed')
        full.final_client_process_census(nonce)
    except Exception:
        suite=empty_report(nonce); suite.update(status='failed',failure_kind='export_failed')
    report['stage3']=suite
    outputs=[]
    if report['status']=='ok' and suite['status']=='ok':
        try:
            if len(suite['cases'])!=1 or suite['cases'][0]['name']!=CASE: raise full.FullError('invalid_result')
            case=suite['cases'][0]; raw=full.secure_bytes(root/(CASE+'.out'),MAX_OUTPUT)
            validate_observations(raw)
            if case['status']!='ok' or len(raw)!=case['output_size'] or full.digest(raw)!=case['output_sha256']:
                raise full.FullError('invalid_result')
            outputs=[{'name':CASE+'.out','size':len(raw),'sha256':full.digest(raw),'data_b64':base64.b64encode(raw).decode('ascii')}]
            report['native_tests_completed']=True
        except Exception: suite.update(status='failed',failure_kind='export_failed')
    if suite['status']!='ok':
        outputs=[]; report.update(status='stage3_failed',native_tests_completed=False)
    raw=json.dumps({'schema':WIRE_SCHEMA,'profile':PROFILE,'nonce':nonce,'report':report,'outputs':outputs},
                   sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'
    if len(json.dumps(report,separators=(',',':')).encode())>full.MAX_REPORT or len(raw)>MAX_TRANSPORT:
        raise full.FullError('export_failed')
    return raw
