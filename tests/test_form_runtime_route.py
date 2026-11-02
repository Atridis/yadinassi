import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from form_runtime_packet import route, SOURCE_SHA256
from yadinassi.syntax.parser import parse
from yadinassi.syntax import ast

NONCE='a'*32


def files():
    launcher=ROOT/'integrational_tests/launcher_1c'
    result={p:(launcher/p).read_bytes() for p in ('Launcher.xml','Launcher/Forms/Main.xml','Launcher/Ext/ObjectModule.bsl')}
    result['Launcher/Forms/Main/Ext/Form.xml']=route.form_xml()
    result['Launcher/Forms/Main/Ext/Form/Module.bsl']=route.module()
    return result


def marker(phase='completed'):
    values=['ok']*40;values[23]='server-create';values[24]='server-create:client-open'
    records=''.join('MF'+str(i)+'='+v+'|' for i,v in enumerate(values,1)) if phase=='completed' else ''
    return {'schema':route.SCHEMA,'nonce':NONCE,'phase':phase,'source_sha256':SOURCE_SHA256,
            'form_sha256':route.FORM_SHA256,'records':records}


class FormRouteTests(unittest.TestCase):
    def test_source_sides_and_wrapper_budget(self):
        module=route.module();self.assertLessEqual(len(module),8192)
        routines={n.name:n for n in parse(module.decode('utf-8'),'<form-oracle>') if isinstance(n,ast.Routine)}
        self.assertEqual(routines['FormCreate'].execution_context,'server')
        self.assertEqual(routines['FormOpen'].execution_context,'client')
        self.assertEqual(routines['FormObserve'].execution_context,'client')
        self.assertEqual(routines['ServerRead'].execution_context,'server')
        self.assertNotIn(b'ErrorDescription',module)
        self.assertNotIn('ОписаниеОшибки'.encode(),module)
        self.assertEqual(module.count(b'Procedure FormOpen('),1)

    def test_redump_exact_owned_module_and_routing(self):
        data=files();self.assertEqual(len(route.validate_redump(data)),64)
        normalized=dict(data)
        normalized['Launcher/Forms/Main/Ext/Form/Module.bsl']=b'\xef\xbb\xbf'+route.module().replace(b'\n',b'\r\n')
        self.assertEqual(route.validate_redump(data),route.validate_redump(normalized))
        for key,before,after in (
            ('Launcher/Forms/Main/Ext/Form.xml',b'OnCreateAtServer',b'OnOpen'),
            ('Launcher/Forms/Main/Ext/Form.xml',b'http://v8.1c.ru/8.1/data/enterprise/current-config',b'http://invalid-config'),
            ('Launcher/Forms/Main/Ext/Form.xml',b'<MainAttribute>true',b'<MainAttribute>false'),
            ('Launcher.xml',b'<DefaultForm>',b'<Foreign><DefaultForm>'),
            ('Launcher/Forms/Main/Ext/Form.xml',b'cfg:ExternalDataProcessorObject.Launcher',b'cfg:ExternalDataProcessorObject.Other'),
            ('Launcher/Forms/Main/Ext/Form.xml',b'<Events>',b'<Enabled>false</Enabled><Events>'),
            ('Launcher/Forms/Main/Ext/Form.xml',b'http://v8.1c.ru/8.3/xcf/logform',b'http://invalid'),
            ('Launcher.xml',b'http://v8.1c.ru/8.3/MDClasses',b'http://invalid'),
            ('Launcher/Forms/Main.xml',b'Managed',b'Ordinary'),
            ('Launcher.xml',b'ExternalDataProcessor.Launcher.Form.Main',b'ExternalDataProcessor.Other.Form.Main'),
            ('Launcher/Forms/Main/Ext/Form/Module.bsl',b'&AtServer',b'&AtClient')):
            changed=dict(data);changed[key]=data[key].replace(before,after,1)
            with self.assertRaises(ValueError):route.validate_redump(changed)
        displaced=dict(data);displaced['Launcher.xml']=data['Launcher.xml'].replace(b'<DefaultForm>',b'<Foreign><DefaultForm>').replace(b'</DefaultForm>',b'</DefaultForm></Foreign>')
        with self.assertRaises(ValueError):route.validate_redump(displaced)
        relocated=dict(data)
        declaration=b' xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config"'
        relocated['Launcher/Forms/Main/Ext/Form.xml']=route.form_xml().replace(declaration,b'').replace(b'<AutoCommandBar',b'<AutoCommandBar'+declaration)
        with self.assertRaises(ValueError):route.validate_redump(relocated)
        encoded=dict(data); encoded['Launcher/Forms/Main/Ext/Form.xml']=route.form_xml().decode('utf-8').encode('utf-16')
        with self.assertRaises(ValueError):route.validate_redump(encoded)
        changed=dict(data);changed['Launcher/Ext/ObjectModule.bsl']=b'Message("not owned");'
        with self.assertRaises(ValueError):route.validate_redump(changed)

    def test_private_marker_strict_binding(self):
        raw=json.dumps(marker()).encode()
        self.assertEqual(len(route.marker(raw,NONCE,'completed')),40)
        self.assertEqual(route.marker(json.dumps(marker('entered')).encode(),NONCE,'entered'),())
        for key,value in (('nonce','b'*32),('phase','error'),('source_sha256','0'*64),('form_sha256','0'*64)):
            changed=marker();changed[key]=value
            with self.assertRaises(ValueError):route.marker(json.dumps(changed).encode(),NONCE,'completed')
        with self.assertRaises(ValueError):route.marker(raw.replace(b'"schema":',b'"schema":"duplicate","schema":'),NONCE,'completed')
        changed=marker();changed['records']=changed['records'].replace('MF1=ok','MF1=!E')
        with self.assertRaises(ValueError):route.marker(json.dumps(changed).encode(),NONCE,'completed')
        changed=marker();changed['records']=changed['records'].replace('server-create:client-open','client-open')
        with self.assertRaises(ValueError):route.marker(json.dumps(changed).encode(),NONCE,'completed')
        with self.assertRaises(ValueError):route.marker(b' '*8193,NONCE,'completed')
