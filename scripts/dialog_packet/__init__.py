"""Closed six-flow native dialog acquisition. No native execution on import."""
from pathlib import Path
import hashlib
import re
ROOT = Path(__file__).resolve().parent
MAX_SOURCE = 16384
MAX_OUTPUT = 4096
COUNT = 6
PACKET_HASHES = {'Launcher.xml': '719b5df645763c6adf04ccc9aa0265a312cf1677edb633dd702dd783258fe0bd', 'Launcher/Ext/ObjectModule.bsl': 'ce374bb1fcaa576083528b13c364059bb10cdd833534a73f66719b3fab5995fe', 'Launcher/Forms/Main.xml': 'b21910e73df0952f79708abe9122615d545e41e498da8a6aa5396594d4ffdcb2', 'Launcher/Forms/Main/Ext/Form.xml': '06bb1943fcc9ab460baa9a143717b24e53f14d684ad8023c9f386b7a742d3de5', 'Launcher/Forms/Main/Ext/Form/Module.bsl': 'b0bedb9b8442635d7c0d5d397bbaf4912ac25e1f9c449000860667a6c9455d98'}
SOURCE_SHA256 = hashlib.sha256(b''.join(p.encode()+b'\0'+bytes.fromhex(h) for p,h in sorted(PACKET_HASHES.items()))).hexdigest()
FORM_SHA256 = hashlib.sha256(b''.join(p.encode()+b'\0'+bytes.fromhex(h) for p,h in sorted(PACKET_HASHES.items()) if p.endswith('.xml'))).hexdigest()


def packet():
    values={}
    for name,digest in PACKET_HASHES.items():
        path=ROOT/name
        if path.is_symlink() or not path.is_file():raise ValueError('packet shape')
        raw=path.read_bytes()
        if not 0<len(raw)<=MAX_SOURCE or hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('packet identity')
        values[name]=raw
    return values


def parse_records(raw):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_OUTPUT:raise ValueError('record budget')
    parts=raw.decode('ascii').split('|')
    if len(parts)!=7 or parts[-1]!='':raise ValueError('record inventory')
    result=[]
    for number,part in enumerate(parts[:-1],1):
        match=re.fullmatch(r'DG([1-6])=1;(ok|cancel|yes|no|timeout|warning|other);([01]);([a-z,]+)',part)
        if not match or int(match[1])!=number:raise ValueError('record shape')
        events=match[4].split(',')
        if events not in (['start','returned','callback','finish',''],['start','callback','returned','finish','']):raise ValueError('event order')
        result.append((match[2],int(match[3]),tuple(events[:-1])))
    return tuple(result)


def require_available(records):
    if type(records) is not tuple or len(records)!=COUNT:raise ValueError('incomplete observation')
    return records
