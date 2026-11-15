"""Sixteen client-only native reuse observations; no execution on import."""
from pathlib import Path
import hashlib
import re
ROOT=Path(__file__).resolve().parent
MAX_SOURCE=32768
MAX_OUTPUT=4096
COUNT=16
PACKET_HASHES={'Launcher.xml': '719b5df645763c6adf04ccc9aa0265a312cf1677edb633dd702dd783258fe0bd', 'CommonModules/ReuseSession.xml': 'e47bf0fc3b293644dda3d359f3778a55f1d4f11343e7e98cf4e7a5a3ee663fc4', 'CommonModules/ReuseRequest.xml': '7a64367de5123af3dcca51bd43e3b5c8d967699a9d90e114aa810cfbc1e9d267', 'CommonModules/ReuseRequest/Ext/Module.bsl': '0012c318e5bd897860261b6f170c591061fb0523e9cc80539be8e1446d026433', 'CommonModules/ReuseSession/Ext/Module.bsl': 'c712db97141dd167933ed6aeac7020bca3e48ffef8fd01573f2f41b25a0a1c86', 'Launcher/Forms/Main.xml': 'b21910e73df0952f79708abe9122615d545e41e498da8a6aa5396594d4ffdcb2', 'Launcher/Ext/ObjectModule.bsl': 'ce374bb1fcaa576083528b13c364059bb10cdd833534a73f66719b3fab5995fe', 'Launcher/Forms/Main/Ext/Form.xml': '06bb1943fcc9ab460baa9a143717b24e53f14d684ad8023c9f386b7a742d3de5', 'Launcher/Forms/Main/Ext/Form/Module.bsl': 'dbf0a7ee6bd2667e4411a26230c76abdcea3ecc9d8333910e2b366e8f72a6daa'}
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
        match=re.fullmatch(r'CM([1-9][0-9]?)=(error|[0-9]{1,2}(?::[0-9]{1,2}){0,3})',part)
        if not match or int(match[1])!=number:raise ValueError('record shape')
        result.append(match[2])
    return tuple(result)

def require_available(records):
    if type(records) is not tuple or len(records)!=COUNT:raise ValueError('incomplete observation')
    return records
