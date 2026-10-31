"""Closed tree-v1 native measurement; never the ordinary six-output contract."""
import base64
import json
import re
import full_suite as full
import native_1c_tree_profiles as profiles
PROFILE = 'tree-v1'
WIRE_SCHEMA = 'native-1c-tree-v1'
STAGE_SCHEMA = 'native-1c-tree-stage-v1'
SOURCE = 'integrational_tests/measurements/tree_fill_values.bsl'
TARGET = 'scenarios/tree_fill_values.bsl'
CASE = 'tree_fill_values'
SOURCE_SHA256 = '58d466f3a9a181891fd97e205d115f0ce32b620f8fa8df3d56f4516405a65c90'
COUNT = 34
MAX_OUTPUT = 8192
MAX_TRANSPORT = 65536
def input_files(*, profile='tree-v1'):
    spec = profiles.select(profile)
    return {
        **{k:v for k,v in full.INPUT_FILES.items() if not k.startswith('integrational_tests/tests/')},
        full.CLIENT_SOURCE: full.CLIENT_TARGET,
        'scripts/native_1c_bootstrap/tree_suite.py': 'bootstrap/tree_suite.py',
        'scripts/native_1c_tree_profiles.py': 'bootstrap/native_1c_tree_profiles.py',
        **({'scripts/native_1c_tree_copy_diagnostics.py': 'bootstrap/native_1c_tree_copy_diagnostics.py', 'scripts/native_1c_tree_access_probe.py': 'bootstrap/native_1c_tree_access_probe.py'} if profile == 'tree-copy-v1' else {}),
        **({'scripts/native_1c_tree_columns_move_contract.py': 'bootstrap/native_1c_tree_columns_move_contract.py'} if profile in ('tree-columns-move-boundary-v1', 'tree-columns-move-tail-v1') else {}),
        **({'scripts/native_1c_tree_columns_clear_contract.py': 'bootstrap/native_1c_tree_columns_clear_contract.py'} if profile in ('tree-columns-clear-lifetime-v1', 'tree-columns-clear-metadata-v1', 'tree-columns-delete-v1', 'tree-columns-delete-string-v1') else {}),
        'scripts/' + spec.contract + '.py': 'bootstrap/' + spec.contract + '.py',
        spec.source: spec.target,
    }

INPUT_FILES = input_files()



def empty_report(nonce, *, profile='tree-v1'):
    spec = profiles.select(profile)
    if not full.valid_nonce(nonce): raise full.FullError('invalid_input')
    return {'schema':spec.stage_schema,'profile':spec.name,'nonce':nonce,'status':'not_started',
        'failure_kind':'prerequisites_failed','failed_case':None,'input_sha256':{},
        'observation_diagnostic':None,
        **({'copy_access_probes':{'server':None,'client':None}} if profile == 'tree-copy-v1' else {}),
        'cases':[{'name':spec.case,'status':'not_started','source_sha256':None,'module_sha256':None,
                  'output_sha256':None,'output_size':None,'message_count':None}],
        'client_tree':full.empty_dates_report()}


def input_hashes(inputs, *, profile='tree-v1'):
    spec = profiles.select(profile)
    return {k:full.digest(full.secure_bytes(inputs/v, full.MAX_OUTPUT)) for k,v in input_files(profile=profile).items()}


DIAGNOSTIC_CATEGORIES = frozenset(('invalid_type','output_limit','encoding','record_count',
    'calibration','api_controls','record_shape','probe_b','probe_p','probe_q','probe_r','payload_contract'))
CALIBRATION_CODES = '0123456789ABCDEFGHIJKLMNOPQR'


class ObservationFailure(full.FullError):
    def __init__(self, diagnostic):
        super().__init__('unsupported_observation')
        self.diagnostic = diagnostic


def observation_diagnostic(raw, site, *, profile='tree-v1'):
    spec = profiles.select(profile)
    if profile == 'tree-copy-v1':
        import native_1c_tree_copy_contract as contract
        import native_1c_tree_copy_diagnostics as diagnostic
        import native_1c_tree_access_probe as probe
        try:
            record, main = probe.split_capture(raw)
            if not probe.scalar_controls_valid(record): raise probe.ProbeError('controls')
        except probe.ProbeError:
            return {'site':site,'case':None,'category':'access_probe','calibration':None}
        return diagnostic.observation_diagnostic(main, site, contract.validate_payload, contract.ObservationError)
    if profile in ('tree-sort-v1', 'tree-columns-move-v1', 'tree-columns-move-boundary-v1', 'tree-columns-move-tail-v1', 'tree-columns-clear-v1', 'tree-columns-clear-lifetime-v1', 'tree-columns-clear-metadata-v1', 'tree-columns-delete-v1', 'tree-columns-delete-string-v1', 'format-numbers-v1', 'format-dates-v1', 'json-family-v1', 'file-io-family-v1'):
        if profile == 'file-io-family-v1':
            import native_1c_file_io_family_contract as contract
        elif profile == 'json-family-v1':
            import native_1c_json_family_contract as contract
        elif profile == 'format-dates-v1':
            import native_1c_format_dates_contract as contract
        elif profile == 'format-numbers-v1':
            import native_1c_format_numbers_contract as contract
        elif profile == 'tree-sort-v1':
            import native_1c_tree_sort_contract as contract
        elif profile == 'tree-columns-move-v1':
            import native_1c_tree_columns_move_contract as contract
        elif profile == 'tree-columns-move-boundary-v1':
            import native_1c_tree_columns_move_boundary_contract as contract
        elif profile == 'tree-columns-move-tail-v1':
            import native_1c_tree_columns_move_tail_contract as contract
        elif profile == 'tree-columns-delete-v1':
            import native_1c_tree_columns_delete_contract as contract
        elif profile == 'tree-columns-delete-string-v1':
            import native_1c_tree_columns_delete_string_contract as contract
        elif profile == 'tree-columns-clear-metadata-v1':
            import native_1c_tree_columns_clear_metadata_contract as contract
        elif profile == 'tree-columns-clear-lifetime-v1':
            import native_1c_tree_columns_clear_lifetime_contract as contract
        elif profile == 'tree-columns-clear-v1':
            import native_1c_tree_columns_clear_contract as contract
        else:
            raise full.FullError('invalid_input')
        if site not in ('server', 'client'): raise full.FullError('invalid_input')
        try:
            contract.validate_output(raw)
        except contract.ObservationError:
            return {'site':site,'case':None,'category':'record_count','calibration':None}
        return None
    from native_1c_tree_fill_contract import validate_payload, validate_api_payload, ObservationError
    if site not in ('server','client'): raise full.FullError('invalid_input')
    def result(category, case=None, calibration=None):
        return {'site':site,'case':case,'category':category,'calibration':calibration}
    if type(raw) is not bytes: return result('invalid_type')
    if len(raw)>MAX_OUTPUT: return result('output_limit')
    if any(value<32 and value!=10 or value>126 for value in raw): return result('encoding')
    lines=raw.splitlines(keepends=True)
    if len(lines)!=spec.count: return result('record_count')
    if lines[0]!=b'TF-C: [-]\n':
        match=re.fullmatch(rb'TF-C: \[([0-9A-R])\]\n',lines[0])
        return result('calibration',0,match[1].decode() if match else None)
    for case,line in enumerate(lines[1:33],1):
        prefix=f'TF-{case}: ['.encode()
        if not line.startswith(prefix) or not line.endswith(b']\n'):
            return result('record_shape',case)
        value=line[len(prefix):-2]
        if value in (b'B',b'P',b'Q',b'R'): return result('probe_'+value.decode().lower(),case)
        try: validate_payload(value,case)
        except ObservationError: return result('payload_contract',case)
    if not lines[-1].startswith(b'TF-A: [') or not lines[-1].endswith(b']\n'):
        return result('api_controls')
    try: validate_api_payload(lines[-1][7:-2])
    except ObservationError: return result('api_controls')
    return None


def validate_diagnostic(value, *, profile='tree-v1'):
    spec = profiles.select(profile)
    if profile == 'tree-copy-v1':
        import native_1c_tree_copy_diagnostics as diagnostic
        try:
            return diagnostic.validate_diagnostic(value)
        except diagnostic.DiagnosticError:
            raise full.FullError('invalid_result') from None
    if profile in ('tree-sort-v1', 'tree-columns-move-v1', 'tree-columns-move-boundary-v1', 'tree-columns-move-tail-v1', 'tree-columns-clear-v1', 'tree-columns-clear-lifetime-v1', 'tree-columns-clear-metadata-v1', 'tree-columns-delete-v1', 'tree-columns-delete-string-v1', 'format-numbers-v1', 'format-dates-v1', 'json-family-v1', 'file-io-family-v1'):
        if value is not None and (type(value) is not dict or value != {
                'site':value.get('site'),'case':None,'category':'record_count','calibration':None}
                or type(value['site']) is not str or value['site'] not in ('server','client')):
            raise full.FullError('invalid_result')
        return
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
            or (category in ('invalid_type','output_limit','encoding','record_count','api_controls') and value['case'] is not None)
            or (category!='calibration' and value['calibration'] is not None)):
        raise full.FullError('invalid_result')


def validate_observations(raw, site='server', *, profile='tree-v1'):
    spec = profiles.select(profile)
    if profile == 'file-io-family-v1':
        from native_1c_file_io_family_contract import validate_output, ObservationError
    elif profile == 'json-family-v1':
        from native_1c_json_family_contract import validate_output, ObservationError
    elif profile == 'format-dates-v1':
        from native_1c_format_dates_contract import validate_output, ObservationError
    elif profile == 'format-numbers-v1':
        from native_1c_format_numbers_contract import validate_output, ObservationError
    elif profile == 'tree-v1':
        from native_1c_tree_fill_contract import validate_output, ObservationError
    elif profile == 'tree-copy-v1':
        from native_1c_tree_copy_contract import validate_output, ObservationError
    elif profile == 'tree-sort-v1':
        from native_1c_tree_sort_contract import validate_output, ObservationError
    elif profile == 'tree-columns-move-v1':
        from native_1c_tree_columns_move_contract import validate_output, ObservationError
    elif profile == 'tree-columns-move-boundary-v1':
        from native_1c_tree_columns_move_boundary_contract import validate_output, ObservationError
    elif profile == 'tree-columns-move-tail-v1':
        from native_1c_tree_columns_move_tail_contract import validate_output, ObservationError
    elif profile == 'tree-columns-delete-v1':
        from native_1c_tree_columns_delete_contract import validate_output, ObservationError
    elif profile == 'tree-columns-delete-string-v1':
        from native_1c_tree_columns_delete_string_contract import validate_output, ObservationError
    elif profile == 'tree-columns-clear-metadata-v1':
        from native_1c_tree_columns_clear_metadata_contract import validate_output, ObservationError
    elif profile == 'tree-columns-clear-lifetime-v1':
        from native_1c_tree_columns_clear_lifetime_contract import validate_output, ObservationError
    elif profile == 'tree-columns-clear-v1':
        from native_1c_tree_columns_clear_contract import validate_output, ObservationError
    else:
        raise full.FullError('invalid_input')
    if profile == 'tree-copy-v1':
        import native_1c_tree_access_probe as probe
        diagnostic = observation_diagnostic(raw, site, profile=profile)
        if diagnostic is not None: raise ObservationFailure(diagnostic)
        _, main = probe.split_capture(raw)
        return validate_output(main)
    try: return validate_output(raw)
    except ObservationError:
        diagnostic=observation_diagnostic(raw,site, profile=profile)
        if diagnostic is None: diagnostic={'site':site,'case':None,'category':'record_count','calibration':None}
        validate_diagnostic(diagnostic, profile=profile)
        raise ObservationFailure(diagnostic) from None


def client_module(source, template, *, profile='tree-v1'):
    spec = profiles.select(profile)
    if (type(source) is not bytes or full.digest(source) != spec.source_sha256
            or full.digest(template) != full.PREPROCESSOR_SOURCE_SHA256):
        raise full.FullError('invalid_input')
    original = source.decode('utf-8')
    marker = spec.calibration_marker
    if ('\r' in original or 'TreeLane' in original or original.count(marker)!=1
            or original.count('Сообщить(')!=spec.print_sites): raise full.FullError('invalid_input')
    split=original.index(marker)+1
    declarations=re.sub(r'(?m)^(Функция |Процедура )',r'&НаКлиенте\n\1',original[:split])
    body=original[split:].replace('Сообщить(', 'TreeLaneCapture(')
    inverse=re.sub(r'(?m)^&НаКлиенте\n(?=Функция |Процедура )','',declarations)
    inverse+=body.replace('TreeLaneCapture(', 'Сообщить(')
    if inverse!=original: raise full.FullError('invalid_input')
    # Format's bounded observer emits inside a helper procedure. Capture those
    # calls too; the exact source pin and inverse above still bind all inputs.
    if profile in ('format-numbers-v1', 'format-dates-v1', 'json-family-v1', 'file-io-family-v1'):
        declarations = declarations.replace('Сообщить(', 'TreeLaneCapture(')
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
    harness=harness.replace(wire, '        "' + spec.name + '", Номер, Фаза, Контекст, Значения));')
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
    Если TreeLaneMessages.Count() >= {spec.count} Или TreeLaneCharacters + СтрДлина(Text) > {MAX_OUTPUT-spec.count} Тогда
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
    if profile in ('tree-copy-v1', 'tree-sort-v1', 'tree-columns-move-v1', 'tree-columns-move-boundary-v1', 'tree-columns-move-tail-v1', 'tree-columns-clear-v1', 'tree-columns-clear-lifetime-v1', 'tree-columns-clear-metadata-v1', 'tree-columns-delete-v1', 'tree-columns-delete-string-v1'):
        wrapper = wrapper.replace('Или Code = 95;', 'Или Code = 95 Или Code = 47;')
    if profile in ('format-numbers-v1', 'format-dates-v1', 'json-family-v1', 'file-io-family-v1'):
        wrapper = wrapper.replace('Или Code = 95;', 'Или Code = 95 Или Code = 124;')
    if profile == 'tree-columns-clear-lifetime-v1':
        wrapper = wrapper.replace('Или Code = 47;', 'Или Code = 47 Или Code = 126;')
    return full.generated_module((prefix+harness[:fixed.start()]+wrapper+harness[fixed.end():]).encode('utf-8'))


def client_marker(path, nonce, phase, *, profile='tree-v1'):
    spec = profiles.select(profile)
    if not full.valid_nonce(nonce) or phase not in ('entered','completed'): raise full.FullError('invalid_input')
    value=full.strict_json(full.secure_bytes(path,16384),max_depth=3)
    if (type(value) is not dict or set(value)!={'schema','nonce','phase','witness','values'}
            or value['schema']!=spec.name or value['nonce']!=nonce or value['phase']!=phase
            or value['witness']!='client' or type(value['values']) is not list
            or len(value['values'])!=(0 if phase=='entered' else spec.count)
            or any(type(v) is not str for v in value['values'])): raise full.FullError('invalid_result')
    if phase=='completed': validate_observations(full.serialize_messages(value['values']), 'client', profile=profile)
    return value


def run_suite(launcher, platform, launcher_epf, root, inputs, nonce, *, profile='tree-v1'):
    spec = profiles.select(profile)
    report=empty_report(nonce, profile=profile)
    report.update(status='failed',failure_kind='unexpected_failure')
    case=report['cases'][0]
    old=launcher.read_result,launcher.run_process,launcher.build_epf
    try:
        if platform.timeout!=120 or platform.user!='NativeSmoke' or platform.password is not None:
            raise full.FullError('invalid_input')
        report['input_sha256']=input_hashes(inputs, profile=profile)
        if report['input_sha256'][spec.source]!=spec.source_sha256: raise full.FullError('invalid_input')
        full.absent(root); root.mkdir(mode=0o700)
        report['failed_case']=spec.case; case['status']='failed'
        raw=full.secure_bytes(inputs/spec.target,full.MAX_OUTPUT)
        if full.digest(raw)!=spec.source_sha256: raise full.FullError('invalid_input')
        case['source_sha256']=spec.source_sha256
        expected=full.generated_module(raw)
        directory,output=root/(spec.case+'-case'),root/(spec.case+'.out')
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
        full.absent(directory,output,root/(spec.case+'.err'),output.with_suffix('.out.tmp'))
        launcher.run_case(platform,inputs/spec.target,launcher_epf,directory,output)
        full.require_zero_result(directory/'TestModule.build-result.txt',0)
        full.require_epf(directory/'TestModule.epf')
        if full.secure_bytes(directory/'src/TestModule/Ext/ObjectModule.bsl',full.MAX_OUTPUT+3)!=expected:
            raise full.FullError('module_mismatch')
        messages,_=full.read_native_result(directory/'result.json')
        actual=full.secure_bytes(output,MAX_OUTPUT)
        if len(messages)!=spec.count or actual!=full.serialize_messages(messages): raise full.FullError('output_mismatch')
        full.absent(root/(spec.case+'.err'),directory/'result.err')
        if profile == 'tree-copy-v1':
            import native_1c_tree_access_probe as probe
            try:
                report['copy_access_probes']['server'] = probe.witness(actual, 'server', nonce, spec.source_sha256, full.digest(expected))
            except probe.ProbeError:
                pass  # Strict observation validation below rejects malformed probes.
        validate_observations(actual, profile=profile)
        case.update(status='ok',module_sha256=full.digest(expected),output_sha256=full.digest(actual),output_size=len(actual),message_count=spec.count)
        report['failed_case']=None
        report['client_tree']=full.run_client_probe(platform,root/'client-tree',inputs,nonce,report['input_sha256'],tree_output=output, tree_profile=profile)
        report['observation_diagnostic']=report['client_tree'].pop('observation_diagnostic',None)
        if profile == 'tree-copy-v1': report['copy_access_probes']['client'] = report['client_tree'].pop('copy_access_probe',None)
        if report['client_tree']['status']!='ok': raise full.FullError(report['client_tree']['failure_kind'])
        if input_hashes(inputs, profile=profile)!=report['input_sha256']: raise full.FullError('invalid_input')
        report.update(status='ok',failure_kind='none')
    except Exception as error:
        if isinstance(error,ObservationFailure): report['observation_diagnostic']=error.diagnostic
        report['failure_kind']=error.kind if isinstance(error,full.FullError) else 'unexpected_failure'
    finally:
        launcher.read_result,launcher.run_process,launcher.build_epf=old
    return report


def write_report(path,report, *, profile='tree-v1'):
    spec = profiles.select(profile)
    raw=json.dumps(report,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if len(raw)>full.MAX_STAGE_REPORT: raise full.FullError('export_failed')
    with path.open('xb') as stream: stream.write(raw)


def finish_report(report,nonce,root,*,quiet,bus_cleanup_failed, profile='tree-v1'):
    spec = profiles.select(profile)
    suite=empty_report(nonce, profile=profile)
    try:
        path=root.parent/'stage3-report.json'
        if path.exists() or path.is_symlink(): suite=full.strict_json(full.secure_bytes(path,full.MAX_STAGE_REPORT))
        if (type(suite) is not dict or suite.get('schema')!=spec.stage_schema
                or suite.get('profile')!=spec.name or suite.get('nonce')!=nonce): raise full.FullError('invalid_result')
        if not quiet or bus_cleanup_failed: raise full.FullError('process_failed')
        full.final_client_process_census(nonce)
    except Exception:
        suite=empty_report(nonce, profile=profile); suite.update(status='failed',failure_kind='export_failed')
    report['stage3']=suite
    outputs=[]
    if report['status']=='ok' and suite['status']=='ok':
        try:
            if len(suite['cases'])!=1 or suite['cases'][0]['name']!=spec.case: raise full.FullError('invalid_result')
            case=suite['cases'][0]; raw=full.secure_bytes(root/(spec.case+'.out'),MAX_OUTPUT)
            validate_observations(raw, profile=profile)
            if case['status']!='ok' or len(raw)!=case['output_size'] or full.digest(raw)!=case['output_sha256']:
                raise full.FullError('invalid_result')
            outputs=[{'name':spec.case+'.out','size':len(raw),'sha256':full.digest(raw),'data_b64':base64.b64encode(raw).decode('ascii')}]
            report['native_tests_completed']=True
        except Exception: suite.update(status='failed',failure_kind='export_failed')
    if suite['status']!='ok':
        outputs=[]; report.update(status='stage3_failed',native_tests_completed=False)
    raw=json.dumps({'schema':spec.schema,'profile':spec.name,'nonce':nonce,'report':report,'outputs':outputs},
                   sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'
    if len(json.dumps(report,separators=(',',':')).encode())>full.MAX_REPORT or len(raw)>MAX_TRANSPORT:
        raise full.FullError('export_failed')
    return raw
