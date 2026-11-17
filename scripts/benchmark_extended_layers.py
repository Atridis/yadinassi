"""Extended Python/classes/direct reference; no performance thresholds."""
import argparse
from contextlib import ExitStack
from dataclasses import dataclass, field
from decimal import Decimal as D, ROUND_HALF_UP
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import math
import os
import stat
import sqlite3
import statistics
import sys
import time
import xml.etree.ElementTree as ET

ROOT = next(parent for parent in Path(__file__).resolve().parents
            if (parent / 'pyproject.toml').is_file() and (parent / 'yadinassi').is_dir())
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from yadinassi import Interpreter
from yadinassi.experimental_naked_collections import UnsupportedNakedSyntax
from yadinassi.python_direct import PythonDirectUnsupported
from yadinassi.syntax.parser import parse
from yadinassi.structures import BSLStructure
from yadinassi.values import BSLArray
from yadinassi.value_tables import BSLValueTable
from yadinassi.value_lists import BSLValueList
from yadinassi.json_processing import BSLJSONWriter, BSLJSONReader, read_json
from yadinassi.file_io import BSLFile, BSLBinaryData
from yadinassi.xml_io import BSLXMLReader, BSLXMLNodeType
from yadinassi.xml_writer import BSLXMLWriter
from scripts.benchmark_execution_layers import metadata
from scripts.benchmark_summary import ratio_cell
from scripts import performance_summary_labels as labels

LAYERS = ('python', 'python_classes', 'bsl')
CASES = ('structure.fields', 'valuetable.build_scan', 'valuelist.build_scan',
         'types.adjust_value', 'json.roundtrip', 'xml.scalar_codec', 'file.stat', 'file.binary_roundtrip', 'xml.roundtrip',
         'db.count', 'db.update', 'form.event', 'form.open')
PREPARED_CASES = tuple(name for name in CASES if not name.startswith('form.'))


def q(value):
    return '"' + str(value).replace('"', '""') + '"'


@dataclass
class Case:
    name: str
    expected: D
    runs: dict = field(default_factory=dict)
    checks: dict = field(default_factory=dict)
    before: dict = field(default_factory=dict)
    source: str = ''
    api: str = ''
    notes: str = ''
    statuses: dict = field(default_factory=dict)
    allow_unsupported: bool = False
    operations: int = 1


def optional_xml_constructor(case, error):
    # Only this known missing capability may become N/A, not arbitrary regressions.
    return (case.allow_unsupported and case.name == 'xml.roundtrip'
            and 'constructor XMLWriter;' in str(error))


def attach_bsl(case, source, route, stack, context=None):
    case.source = source
    vm = Interpreter(database_context=context) if context else Interpreter()
    stack.callback(vm.close)
    if vm.execution_backend != 'python-direct': raise AssertionError('wrong BSL backend')
    program = parse(source, '<extended-reference:' + case.name + '>')
    case.api = 'execute_prepared(plan)' if route == 'prepared' else 'execute_program(preparsed_ast)'
    if route == 'prepared':
        try:
            plan = vm.prepare_program(program)
        except (UnsupportedNakedSyntax, PythonDirectUnsupported) as error:
            if not optional_xml_constructor(case, error):
                raise
            case.statuses['bsl'] = {'status': 'unsupported', 'reason': str(error)}
            return vm
        execute = lambda: vm.execute_prepared(plan)
        case.api = 'execute_prepared(plan)'
    else:
        execute = lambda: vm.execute_program(program)
        case.api = 'execute_program(preparsed_ast)'
    if vm.execution_backend != 'python-direct': raise AssertionError('wrong BSL backend')
    def run():
        execute()
        return vm.variables['r']
    case.runs['bsl'] = run
    return vm


def database(stack):
    from yadinassi.configuration_main_demo import PROFILE, import_main_demo_configuration
    from yadinassi.database_context import SQLiteDBContext
    root = ROOT / 'examples/demo'
    files = {p.relative_to(root).as_posix(): p.read_bytes()
             for p in root.rglob('*') if p.is_file()}
    configuration = import_main_demo_configuration(files, profile=PROFILE)
    folder = Path(stack.enter_context(TemporaryDirectory(prefix='perf-db-')))
    path = folder / 'reference.sqlite'
    context = SQLiteDBContext.create_main_demo(path, configuration)
    stack.callback(context.close)
    owner = Interpreter(database_context=context)
    stack.callback(owner.close)
    manager = owner._catalogs.get_member('Склады')
    return path, context, owner, manager


def form_source(n):
    return '''&AtServer
Procedure Created(Cancel, StandardProcessing)
 C=Commands.Add("Run");C.Action="Bench";
 B=Items.Add("RunButton",Type("FormButton"));B.CommandName="Run";
EndProcedure
&AtClient
Procedure Bench(Command)
 Counter=0;For I=1 To ''' + str(n) + ''' Do Counter=Counter+I;EndDo;
EndProcedure'''


def make_case(name, n, route, stack, *, catalog_rows=32):
    if type(catalog_rows) is not int or not 1 <= catalog_rows <= 1024:
        raise ValueError('catalog rows must be an integer in 1..1024')
    if name not in CASES or route not in ('default', 'prepared'):
        raise ValueError('unknown case or route')
    if type(n) is not int or not 1 <= n <= 1000:
        raise ValueError('iterations must be an integer in 1..1000')
    if route == 'prepared' and name not in PREPARED_CASES:
        raise ValueError('form lifecycle has no execute_prepared route; use default')
    total = D(n * (n - 1) // 2)
    case = Case(name, total, operations=n)
    observed = {}
    if name == 'structure.fields':
        def native():
            s = {'value': D(0)}; result = D(0)
            for i in range(n):
                s['value'] = D(i); result += s['value']
            return result
        def classes():
            s = BSLStructure('Value', D(0)); result = D(0)
            for i in range(n):
                s.set_member('Value', D(i)); result += s.get_member('Value')
            return result
        source = f'S=New Structure("Value",0);R=0;For I=0 To {n-1} Do S.Value=I;R=R+S.Value;EndDo;'
    elif name in ('valuetable.build_scan', 'valuelist.build_scan'):
        def native():
            values = [{'n': D(i)} for i in range(n)]
            observed['python'] = values
            return sum((row['n'] for row in values), D(0))
        if name.startswith('valuetable'):
            def classes():
                table = BSLValueTable(); table.columns.add('N')
                for i in range(n): table.add().set_member('N', D(i))
                observed['python_classes'] = table
                return sum((table.get(D(i)).get_member('N') for i in range(n)), D(0))
            source = f'T=New ValueTable;T.Columns.Add("N");For I=0 To {n-1} Do Row=T.Add();Row.N=I;EndDo;R=0;For I=0 To {n-1} Do R=R+T.Get(I).N;EndDo;'
        else:
            def classes():
                values = BSLValueList()
                for i in range(n): values.add(D(i))
                observed['python_classes'] = values
                return sum((values.get(D(i)).get_member('Value') for i in range(n)), D(0))
            source = f'T=New ValueList;For I=0 To {n-1} Do T.Add(I);EndDo;R=0;For I=0 To {n-1} Do R=R+T.Get(I).Value;EndDo;'
    elif name == 'types.adjust_value':
        from yadinassi.type_descriptions import BSLTypeDescription
        from yadinassi.type_qualifiers import BSLNumberQualifiers
        case.expected = total + D('0.13')*n
        def native():
            return sum(((D(i)+D('0.125')).quantize(D('0.01'),rounding=ROUND_HALF_UP) for i in range(n)),D(0))
        def classes():
            kind=BSLTypeDescription('Number',BSLNumberQualifiers(D(10),D(2)))
            return sum((kind.adjust_value(D(i)+D('0.125')) for i in range(n)),D(0))
        source=f'K=New TypeDescription("Number",New NumberQualifiers(10,2));R=0;For I=0 To {n-1} Do R=R+K.AdjustValue(I+0.125);EndDo;'
    elif name == 'xml.scalar_codec':
        from yadinassi.xml_values import xml_string,xml_value
        from yadinassi.values import BSLType
        def native():
            return sum((D(format(D(i),'f')) for i in range(n)),D(0))
        def classes():
            return sum((xml_value(BSLType.NUMBER,xml_string(D(i))) for i in range(n)),D(0))
        source=f'K=Type("Number");R=0;For I=0 To {n-1} Do R=R+XMLValue(K,XMLString(I));EndDo;'
    elif name == 'json.roundtrip':
        token = 'ёж<&"\\token'; observed = {}
        case.expected = D(n)
        def native():
            data = [token for _ in range(n)]
            encoded = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
            decoded = json.loads(encoded); observed['python'] = encoded; observed['native_decoded'] = decoded
            return D(len(decoded))
        def classes():
            writer = BSLJSONWriter(); writer.set_string(); writer.write_start_array()
            for _ in range(n): writer.write_value(token)
            writer.write_end_array(); encoded = writer.close(); observed['python_classes'] = encoded
            reader = BSLJSONReader(); reader.set_string(encoded)
            try:
                decoded=read_json(reader);observed['classes_decoded']=decoded
                return D(len(decoded.items))
            finally: reader.close()
        source = f'W=New JSONWriter;W.SetString();W.WriteStartArray();For I=1 To {n} Do W.WriteValue({q(token)});EndDo;W.WriteEndArray();Encoded=W.Close();Reader=New JSONReader;Reader.SetString(Encoded);Decoded=ReadJSON(Reader);R=Decoded.Count();Reader.Close();'
        for layer in ('python', 'python_classes'):
            case.checks[layer] = lambda layer=layer: exact(json.loads(observed[layer]), [token]*n)
        vm = attach_bsl(case, source, route, stack)
        previous_native_check=case.checks['python']
        def check_native():
            previous_native_check();exact(observed['native_decoded'],[token]*n)
        case.checks['python']=check_native
        previous_class_check=case.checks['python_classes']
        def check_classes():
            previous_class_check();exact(list(observed['classes_decoded'].items),[token]*n)
        case.checks['python_classes']=check_classes
        def check_bsl():
            exact(json.loads(vm.variables['encoded']),[token]*n)
            decoded=vm.variables['decoded']
            if type(decoded) is BSLArray: actual=decoded.items
            elif type(decoded) is list: actual=decoded
            else: raise AssertionError('unexpected decoded array representation')
            exact(actual,[token]*n)
        case.checks['bsl'] = check_bsl
        case.runs.update(python=native, python_classes=classes)
        return case
    elif name.startswith('file.'):
        folder = Path(stack.enter_context(TemporaryDirectory(prefix='perf-file-')))
        payload = bytes(range(256)) * 16
        src = folder/'input.bin'; src.write_bytes(payload)
        outputs = {layer: folder/(layer+'.bin') for layer in LAYERS}
        case.expected = D(n * len(payload))
        if name == 'file.stat':
            def native():
                result = D(0)
                for _ in range(n):
                    with src.open('rb') as stream:
                        info = os.fstat(stream.fileno())
                        if not stat.S_ISREG(info.st_mode): raise AssertionError('not a regular file')
                        result += D(info.st_size)
                return result
            def classes():
                return sum((BSLFile(str(src)).size() for _ in range(n)), D(0))
            source = f'R=0;For I=1 To {n} Do F=New File({q(src)});R=R+F.Size();EndDo;'
        else:
            def native():
                result = D(0)
                for _ in range(n):
                    data = src.read_bytes(); outputs['python'].write_bytes(data); result += D(len(data))
                return result
            def classes():
                result = D(0)
                for _ in range(n):
                    data = BSLBinaryData(str(src)); data.write(str(outputs['python_classes'])); result += data.size()
                return result
            source = f'R=0;For I=1 To {n} Do B=New BinaryData({q(src)});B.Write({q(outputs["bsl"])});R=R+B.Size();EndDo;'
            case.checks = {layer: (lambda layer=layer: exact(outputs[layer].read_bytes(), payload)) for layer in LAYERS}
            case.before = {layer:(lambda layer=layer:outputs[layer].unlink(missing_ok=True)) for layer in LAYERS}
        case.notes = 'Warm filesystem/page cache; no fsync/durability claim; identical 4096-byte payload. Size baseline opens/fstats/closes a regular file; BSL adds its access validation.'
    elif name == 'xml.roundtrip':
        observed = {}
        def native():
            root = ET.Element('root')
            for i in range(n): ET.SubElement(root, 'row', {'v': str(D(i))})
            decoded = ET.fromstring(ET.tostring(root, encoding='unicode'))
            observed['python'] = decoded
            values = [D(row.attrib['v']) for row in decoded]
            observed['python_values'] = values
            return sum(values, D(0))
        def classes():
            writer = BSLXMLWriter(); writer.set_string(); writer.write_start_element('root')
            for i in range(n):
                writer.write_start_element('row'); writer.write_attribute('v', str(D(i))); writer.write_end_element()
            writer.write_end_element(); encoded = writer.close()
            observed['python_classes'] = encoded
            reader = BSLXMLReader(); reader.set_string(encoded); result = D(0)
            values = []; observed['classes_values'] = values
            try:
                while reader.read():
                    if reader.get_member('NodeType') is BSLXMLNodeType.START and reader.get_member('Name') == 'row':
                        value = D(reader.get_attribute('v')); values.append(value); result += value
            finally: reader.close()
            return result
        source = f'W=New XMLWriter;W.SetString();W.WriteStartElement("root");For I=0 To {n-1} Do W.WriteStartElement("row");W.WriteAttribute("v",String(I));W.WriteEndElement();EndDo;W.WriteEndElement();Encoded=W.Close();Reader=New XMLReader;Reader.SetString(Encoded);ReadValues=New Array;R=0;While Reader.Read() Do If Reader.NodeType=XMLNodeType.StartElement And Reader.Name="row" Then V=Number(Reader.GetAttribute("v"));ReadValues.Add(V);R=R+V;EndIf;EndDo;Reader.Close();'
        case.allow_unsupported = True
        def verify_xml(tree):
            exact(tree.tag, 'root')
            exact([(row.tag, row.attrib) for row in tree], [('row', {'v': str(i)}) for i in range(n)])
        def check_native_xml():
            verify_xml(observed['python']); exact(observed['python_values'], [D(i) for i in range(n)])
        def check_class_xml():
            verify_xml(ET.fromstring(observed['python_classes'])); exact(observed['classes_values'], [D(i) for i in range(n)])
        case.checks['python'] = check_native_xml
        case.checks['python_classes'] = check_class_xml
        case.notes = 'Host XML classes supported; all paths retain consumed numeric attributes for ordered validation. Current direct constructor may be unsupported. No legacy fallback.'
    elif name.startswith('db.'):
        from yadinassi.queries import BSLQuery
        path, context, owner, manager = database(stack)
        if name == 'db.count':
            for i in range(catalog_rows):
                item = manager.create_item(); item.set_member('Description', 'Bench '+str(i)); item.write()
            connection = sqlite3.connect(path); stack.callback(connection.close)
            from yadinassi.sqlite_query_indexes import register_query_collations
            register_query_collations(connection)
            schema_id = str(manager._schema.identity)
            table = connection.execute('SELECT physical_name FROM catalog_storage_map WHERE catalog_id=?', (schema_id,)).fetchone()[0]
            count_sql = 'SELECT COUNT(*) FROM '+chr(34)+table.replace(chr(34),chr(34)*2)+chr(34)
            case.expected = D(n*catalog_rows)
            def native():
                result = D(0)
                for _ in range(n):
                    result += D(connection.execute(count_sql).fetchone()[0])
                return result
            def classes():
                result = D(0)
                for _ in range(n):
                    cursor = BSLQuery(owner._catalogs, 'SELECT COUNT(*) AS N FROM Catalog.Склады').execute().select()
                    if not cursor.next(): raise AssertionError('missing COUNT row')
                    result += cursor.get_member('N')
                return result
            source = f'R=0;For I=1 To {n} Do Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Склады");S=Q.Execute().Select();S.Next();R=R+S.N;EndDo;'
            case.notes = f'Same SQLite file and {catalog_rows} catalog rows. Raw SQL baseline excludes BSL catalog/query admission.'
        else:
            item = manager.create_item(); item.set_member('Description', 'Initial'); item.write()
            ref = item.get_member('Ref'); case.expected = D(n)
            def classes():
                result = D(0)
                for i in range(1, n+1):
                    value = ref.get_object(ref); value.set_member('Description', str(i)); value.write(); result += 1
                return result
            source = f'R=0;For I=1 To {n} Do A=Ref.GetObject();A.Description=String(I);A.Write();R=R+1;EndDo;'
            case.statuses['python'] = {'status': 'not_comparable', 'reason': 'Raw SQLite UPDATE omits catalog writer semantics.'}
            def verify(): exact(ref.get_object(ref).get_member('Description'), str(n))
            case.checks = {'python_classes': verify, 'bsl': verify}
            def reset():
                value=ref.get_object(ref);value.set_member('Description','Before sample');value.write()
            case.before={'python_classes':reset,'bsl':reset}
            vm = attach_bsl(case, source, route, stack, context); 
            from yadinassi.unique_identifiers import BSLUUID
            vm.variables['ref'] = vm._catalogs.get_member('Склады').get_ref(BSLUUID(str(ref.reference_uuid)))
            case.runs['python_classes'] = classes
            case.notes = 'Read/modify/write one existing catalog item; canonical persisted-value readback after every sample; no raw-SQL speed ratio.'
            return case
        case.runs.update(python=native, python_classes=classes)
        attach_bsl(case, source, route, stack, context)
        return case
    elif name.startswith('form.'):
        from yadinassi.form_runtime import FormSession
        from yadinassi.form_model import BSLFormAttribute
        from yadinassi.type_descriptions import BSLTypeDescription
        code = form_source(n)
        def session():
            return FormSession(code, attributes=(BSLFormAttribute('Counter', BSLTypeDescription('Number')),), bindings={'OnCreateAtServer': 'Created'})
        case.expected = D(n*(n+1)//2) if name == 'form.event' else D(1)
        if name == 'form.event':
            current = session(); stack.callback(current.interpreter.close); current.open()
            if current.interpreter.execution_backend != 'python-direct': raise AssertionError('wrong form backend')
            def event():
                snapshot=current.dispatch('command', revision=current.revision, control='RunButton')
                return dict(snapshot.attributes)['Counter']
            case.runs['bsl'] = event; case.api = 'FormSession.dispatch(command) + snapshot'
        else:
            def opening():
                current = session()
                try:
                    current.open()
                    if current.state != 'open' or current._direct_handlers is None or current.interpreter.execution_backend != 'python-direct': raise AssertionError('form did not open directly')
                    current.dispatch('close', revision=current.revision)
                    if current.state != 'closed': raise AssertionError('form did not close')
                    return D(1)
                finally: current.interpreter.close()
            case.runs['bsl'] = opening; case.api = 'FormSession construction + open + close'
        case.source = code
        case.operations = 1
        case.statuses.update({layer: {'status': 'not_comparable', 'reason': 'No equivalent native/classes managed-form lifecycle.'} for layer in ('python', 'python_classes')})
        case.notes = 'Actual direct form lifecycle; event session setup excluded, open case includes construction/compilation. Only the default table includes this lifecycle; it is not execute_prepared.'
        return case
    else:
        raise ValueError(name)
    case.runs.update(python=native, python_classes=classes)
    vm = attach_bsl(case, source, route, stack)
    if name in ('valuetable.build_scan', 'valuelist.build_scan'):
        field = 'N' if name.startswith('valuetable') else 'Value'
        expected_values = [D(i) for i in range(n)]
        case.checks['python'] = lambda: exact([row['n'] for row in observed['python']], expected_values)
        def check_collection(value):
            exact(D(len(value.rows)) if name.startswith('valuetable') else value.count(), D(n))
            exact([value.get(D(i)).get_member(field) for i in range(n)], expected_values)
        case.checks['python_classes'] = lambda: check_collection(observed['python_classes'])
        case.checks['bsl'] = lambda: check_collection(vm.variables['t'])
    if name == 'xml.roundtrip':
        def check_bsl_xml():
            verify_xml(ET.fromstring(vm.variables['encoded']))
            values = vm.variables['readvalues']
            if type(values) is BSLArray: values = values.items
            exact(values, [D(i) for i in range(n)])
        case.checks['bsl'] = check_bsl_xml
    return case


def exact(actual, expected):
    if type(actual) is not type(expected) or actual != expected:
        raise AssertionError((actual, expected))
    if isinstance(expected, (list, tuple)):
        for left, right in zip(actual, expected): exact(left, right)
    elif isinstance(expected, dict):
        for key in expected: exact(actual[key], expected[key])


def validate(case, layer, result):
    if type(result) is not D or result != case.expected:
        raise AssertionError((case.name, layer, result, case.expected))
    if layer in case.checks: case.checks[layer]()


def measure(name, n, rounds, route):
    if type(rounds) is not int or not 3 <= rounds <= 20:
        raise ValueError('rounds must be an integer in 3..20')
    with ExitStack() as stack:
        start = time.perf_counter_ns(); case = make_case(name, n, route, stack)
        setup = (time.perf_counter_ns()-start)/1e9; first = {}; samples = []
        for layer, run in list(case.runs.items()):
            if layer in case.before: case.before[layer]()
            start = time.perf_counter_ns()
            try: result = run()
            except (UnsupportedNakedSyntax, PythonDirectUnsupported) as error:
                if layer != 'bsl' or not optional_xml_constructor(case, error): raise
                case.statuses[layer] = {'status': 'unsupported', 'reason': str(error)}
                del case.runs[layer]; continue
            first[layer] = (time.perf_counter_ns()-start)/1e9
            validate(case, layer, result)
            if layer in case.before: case.before[layer]()
            validate(case, layer, run())
        layers = [layer for layer in LAYERS if layer in case.runs]
        if not layers:
            raise ValueError('no executable reference layers')
        for turn in range(rounds):
            order = layers[turn % len(layers):]+layers[:turn % len(layers)]
            for layer in order:
                reset_start=time.perf_counter_ns()
                if layer in case.before: case.before[layer]()
                reset_seconds=(time.perf_counter_ns()-reset_start)/1e9
                cpu = time.process_time_ns(); start = time.perf_counter_ns(); result = case.runs[layer]()
                elapsed = (time.perf_counter_ns()-start)/1e9; cpu_elapsed = (time.process_time_ns()-cpu)/1e9
                validate(case, layer, result)
                samples.append({'round': turn, 'layer': layer, 'reset_seconds':reset_seconds,'seconds': elapsed, 'cpu_seconds': cpu_elapsed, 'result': str(result)})
        summary = {}
        for layer in layers:
            values = [s['seconds'] for s in samples if s['layer'] == layer]; med = statistics.median(values)
            summary[layer] = {'median_seconds': med, 'min_seconds': min(values), 'max_seconds': max(values), 'mad_seconds': statistics.median(abs(v-med) for v in values)}
        return {'case': name, 'iterations': n, 'operations': case.operations, 'requested_route': route, 'backend': 'python-direct', 'api': case.api, 'source': case.source,
                'source_sha256': hashlib.sha256(case.source.encode()).hexdigest(), 'expected': str(case.expected), 'notes': case.notes,
                'fixture_and_prepare_seconds': setup, 'first_execution_seconds': first, 'statuses': case.statuses, 'samples': samples, 'summary': summary}


def render(report):
    if report.get('schema') != 'execution-layers-extended-v1' or not report['cases']:
        raise ValueError('invalid extended report')
    routes=' / '.join(labels.ROUTES.get(route, route) for route in sorted({case['requested_route'] for case in report['cases']}))
    lines = ['## Расширенное сравнение производительности: '+routes, '',
             'Коммит: `'+report['environment']['git_head']+'`', '', '| Сценарий | Python, мс | Классы yadinassi, мс | BSL, мс | Классы / Python | BSL / Python | BSL / классы |', '|---|---:|---:|---:|---:|---:|---:|']
    for case in report['cases']:
        values = {k:v['median_seconds'] for k,v in case['summary'].items()}
        if not values or set(values) - set(LAYERS) or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in values.values()):
            raise ValueError('invalid timing')
        if any(status.get('status') not in ('unsupported', 'not_comparable') or not status.get('reason') for status in case['statuses'].values()):
            raise ValueError('invalid layer status')
        if set(case['statuses']) != set(LAYERS) - set(values):
            raise ValueError('missing or contradictory layer status')
        cells = [f'{values[k]*1000:.3f}' if k in values else '—' for k in LAYERS]
        ratios = [ratio_cell(values['bsl']/values[k]) if 'bsl' in values and k in values and values[k]>0 else '—' for k in ('python','python_classes')]
        ratios.insert(0,ratio_cell(values['python_classes']/values['python']) if 'python' in values and 'python_classes' in values and values['python']>0 else '—')
        lines.append('| '+case['case']+' | '+' | '.join(cells+ratios)+' |')
    lines += ['', 'Индикаторы коэффициентов (до округления): 🟩 0 ≤ коэффициент < 2; 🟨 2 ≤ коэффициент ≤ 3; 🟧 коэффициент > 3. Ячейки времени не окрашиваются.', '', 'Медианы после прогрева; подготовка, первые вызовы и все замеры сохранены в JSON. Порогов скорости нет. Недоступные сравнения обозначены явно, а не нулём.', '']
    lines += ['| Подготовка / первый вызов | Общие тестовые данные + подготовка BSL, мс | Первый Python, мс | Первый вызов классов, мс | Первый BSL, мс |', '|---|---:|---:|---:|---:|']
    for case in report['cases']:
        first=case['first_execution_seconds']
        cells=[f'{first[k]*1000:.3f}' if k in first else '—' for k in LAYERS]
        lines.append('| '+case['case']+' | '+f'{case["fixture_and_prepare_seconds"]*1000:.3f}'+' | '+' | '.join(cells)+' |')
    lines.append('')
    api_groups = {}
    for case in report['cases']:
        api_groups.setdefault((case['api'], case['requested_route']), []).append(case['case'])
    shared = {key for key, names in api_groups.items() if len(names) > 1}
    for key, names in api_groups.items():
        if key not in shared:
            continue
        if len(names) == len(report['cases']):
            scope = 'для всех сценариев'
        elif len(shared) == 1:
            exceptions = [case['case'] for case in report['cases'] if case['case'] not in names]
            scope = 'для всех сценариев, кроме ' + ', '.join(exceptions)
        else:
            scope = 'для ' + ', '.join(names)
        lines.append('Общий режим исполнения ' + scope + ': `' + labels.api(key[0]) + '`.')
    lines.append('')
    for case in report['cases']:
        details = []
        if (case['api'], case['requested_route']) not in shared:
            details.append(labels.api(case['api']) + '.')
        if case['notes']:
            details.append(labels.note(case['notes']))
        if case['statuses']:
            details.append('; '.join(labels.LAYERS.get(k,k)+': '+labels.STATUSES.get(v['status'],v['status'])+' ('+labels.reason(v['reason'])+')' for k,v in case['statuses'].items()))
        if details:
            lines.append('- **'+case['case']+'**: ' + ' '.join(details))
    return '\n'.join(lines)+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iterations', type=int, default=64)
    parser.add_argument('--rounds', type=int, default=5)
    parser.add_argument('--bsl-route', choices=('default','prepared'), default='default')
    parser.add_argument('--case', choices=CASES, action='append')
    parser.add_argument('--output', required=True); parser.add_argument('--summary', required=True)
    args = parser.parse_args()
    if not 1<=args.iterations<=1000 or not 3<=args.rounds<=20: parser.error('iterations 1..1000, rounds 3..20')
    selected = args.case or (PREPARED_CASES if args.bsl_route == 'prepared' else CASES)
    if len(set(selected)) != len(selected): parser.error('duplicate case')
    if args.bsl_route == 'prepared' and any(name not in PREPARED_CASES for name in selected):
        parser.error('form lifecycle has no execute_prepared route')
    report = {'schema':'execution-layers-extended-v1', 'environment': metadata(), 'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'cases':[measure(name,args.iterations,args.rounds,args.bsl_route) for name in selected]}
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.summary).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    Path(args.summary).write_text(render(report),encoding='utf-8')

if __name__=='__main__': main()
