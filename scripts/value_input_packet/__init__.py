"""Closed eight-flow native typed input acquisition. No native execution on import."""
from pathlib import Path
import hashlib
import re
ROOT = Path(__file__).resolve().parent
MAX_SOURCE = 16384
MAX_OUTPUT = 4096
COUNT = 8
PACKET_HASHES = {'Launcher/Ext/ObjectModule.bsl': 'ce374bb1fcaa576083528b13c364059bb10cdd833534a73f66719b3fab5995fe', 'Launcher/Forms/Main/Ext/Form/Module.bsl': '73dfe578c67599b5ce1431c7a7860b611fc46356d64a1c1d254373c9fd6f162e', 'Launcher/Forms/Main/Ext/Form.xml': '06bb1943fcc9ab460baa9a143717b24e53f14d684ad8023c9f386b7a742d3de5', 'Launcher/Forms/Main.xml': 'b21910e73df0952f79708abe9122615d545e41e498da8a6aa5396594d4ffdcb2', 'Launcher.xml': '719b5df645763c6adf04ccc9aa0265a312cf1677edb633dd702dd783258fe0bd'}
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
    if len(parts)!=9 or parts[-1]!='':raise ValueError('record inventory')
    result=[]
    for number,part in enumerate(parts[:-1],1):
        match=re.fullmatch(r'VI([1-8])=1;(string|number|date|boolean|undefined|item|other);([01]);([01]);([01]);([a-z,]+)',part)
        if not match or int(match[1])!=number:raise ValueError('record shape')
        events=match[6].split(',')
        if events not in (['start','returned','callback','finish',''],['start','callback','returned','finish','']):raise ValueError('event order')
        result.append((match[2],int(match[3]),int(match[4]),int(match[5]),tuple(events[:-1])))
    return tuple(result)


def require_available(records):
    if type(records) is not tuple or len(records)!=COUNT:raise ValueError('incomplete observation')
    return records
