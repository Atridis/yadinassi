"""Sixteen scalar профиля компиляции observations; no execution on import."""
from pathlib import Path
import hashlib
import re
ROOT=Path(__file__).resolve().parent
MAX_SOURCE=32768
MAX_OUTPUT=4096
COUNT=16
PACKET_HASHES={'Launcher.xml': '719b5df645763c6adf04ccc9aa0265a312cf1677edb633dd702dd783258fe0bd', 'CommonModules/ClientProbe.xml': '0233bdd1754d2cc14640602bdb259d4c8d47f67134564780242dc6782078dae1', 'CommonModules/ServerProbe.xml': '04177af24eb31c3f4e30b5495cd750fb710145adc1cc6cecfaa08273e996ca73', 'CommonModules/DualProbe.xml': '9da37709631d921c1350653a933cf81b61804d4dfc0412fd50d1a9298eada0ee', 'Extensions/Application.bsl': 'de642fbdfcfb59abe59dfba6b6fdf78fce6b4517c0878113ddd32cc867b76819', 'Extensions/Session.bsl': '5f6a733e3b7ea912f4ebdc20c87eb3bbce15bfa5b561d8e8acf0eb9a797b7729', 'SessionParameters/CPState.xml': 'a0da1a6952ce0ae198a467fb7bd8b88f205c1901d849b2d557ebd5827079f31c', 'CommonModules/ServerProbe/Ext/Module.bsl': '41e6fc9c916fcd6ecd2ecd5ef7241f1abe373a2d00ef9132cdcc54d3b422ddf6', 'CommonModules/DualProbe/Ext/Module.bsl': 'c7e1a55424076a78517101ec2c1b5f7f6fe285c3be4f9436aefb0753db3455c3', 'CommonModules/ClientProbe/Ext/Module.bsl': '9fbd060f6c4c38ee17a2d50a02afa76b112023595f5cd6896fc84bf970ac2f15', 'Launcher/Ext/ObjectModule.bsl': 'ce374bb1fcaa576083528b13c364059bb10cdd833534a73f66719b3fab5995fe', 'Launcher/Forms/Main.xml': 'b21910e73df0952f79708abe9122615d545e41e498da8a6aa5396594d4ffdcb2', 'Launcher/Forms/Main/Ext/Form.xml': '06bb1943fcc9ab460baa9a143717b24e53f14d684ad8023c9f386b7a742d3de5', 'Launcher/Forms/Main/Ext/Form/Module.bsl': '5d94d7e6309a6992f0510b159153ab3d4aadb52e278ab14761d9469aad741b7c'}
SOURCE_SHA256=hashlib.sha256(b''.join(p.encode()+b'\0'+bytes.fromhex(h) for p,h in sorted(PACKET_HASHES.items()))).hexdigest()
FORM_SHA256=PACKET_HASHES['Launcher/Forms/Main/Ext/Form.xml']
MODULES_SHA256=hashlib.sha256(b''.join(p.encode()+b'\0'+bytes.fromhex(h) for p,h in sorted(PACKET_HASHES.items()) if p.startswith('CommonModules/'))).hexdigest()

def packet():
    values={}
    for name,digest in PACKET_HASHES.items():
        path=ROOT/name
        if path.is_symlink() or not path.is_file():raise ValueError('packet shape')
        raw=path.read_bytes()
        if not 0<len(raw)<=MAX_SOURCE or hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('packet identity')
        values[name]=raw
    return values

def parse_records(raw, count=COUNT):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_OUTPUT:raise ValueError('record budget')
    parts=raw.decode('ascii').split('|')
    if len(parts)!=count+1 or parts[-1]!='':raise ValueError('record inventory')
    result=[]
    for number,part in enumerate(parts[:-1],1):
        match=re.fullmatch(r'CP([1-9][0-9]?)=([0-9]{1,3}(?::[0-9]{1,3}){0,3})',part)
        if not match or int(match[1])!=number:raise ValueError('record shape')
        result.append(match[2])
    return tuple(result)

def require_available(records):
    if type(records) is not tuple or len(records)!=COUNT:raise ValueError('incomplete observation')
    return records
