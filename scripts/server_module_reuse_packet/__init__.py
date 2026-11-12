"""Sixteen scalar server/client-cache observations; no execution on import."""
from pathlib import Path
import hashlib
import re
ROOT=Path(__file__).resolve().parent
MAX_SOURCE=32768
MAX_OUTPUT=4096
COUNT=16
PACKET_HASHES={'CommonModules/CachedServerCall/Ext/Module.bsl': 'df32644610dd4774a337a616da8d9b678b893409d1866cf4b7f859a2ed5ef76b', 'CommonModules/CachedServerCall.xml': 'fb45abf02ae838bb376d611ac164b6a32a058bd571946e167a94ad5c5b6b94ce', 'CommonModules/ServerInspector/Ext/Module.bsl': 'b223d5dbd11d242c58595029b1e1e531216b0450f354c981fd5b150f00404335', 'CommonModules/ServerInspector.xml': '4bc7738e1d1f3a4327a2a67d0867a256a3e8889ffc24ee9c562751a776c60265', 'CommonModules/ServerRequest/Ext/Module.bsl': 'bdd5c77da2239aff4a6de2a172e022ec62cfe0109176b013567100e18773c2ee', 'CommonModules/ServerRequest.xml': 'f316e1fe13c1dd392adbe6af605fa1221ffe7361bbf344f69111d803af16ceff', 'CommonModules/ServerSession/Ext/Module.bsl': '03f0fc74a1aa8913b8f888c91fe9dfb37b0236a3d8e371aa5aaff36f605d4353', 'CommonModules/ServerSession.xml': '9b8651b2e55f06c572a76b17f8d02bcf2c93edba889d5bc19c9a11bd49563bfb', 'Launcher/Ext/ObjectModule.bsl': 'ce374bb1fcaa576083528b13c364059bb10cdd833534a73f66719b3fab5995fe', 'Launcher/Forms/Main/Ext/Form/Module.bsl': '5b402ae8c2f9554785c8939c26e4524b766178a31ba0a702f97eaa4bfd1dffa6', 'Launcher/Forms/Main/Ext/Form.xml': '06bb1943fcc9ab460baa9a143717b24e53f14d684ad8023c9f386b7a742d3de5', 'Launcher/Forms/Main.xml': 'b21910e73df0952f79708abe9122615d545e41e498da8a6aa5396594d4ffdcb2', 'Launcher.xml': '719b5df645763c6adf04ccc9aa0265a312cf1677edb633dd702dd783258fe0bd'}
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
        match=re.fullmatch(r'SR([1-9][0-9]?)=(error|[0-9]{1,2}(?::[0-9]{1,2}){0,3})',part)
        if not match or int(match[1])!=number:raise ValueError('record shape')
        result.append(match[2])
    return tuple(result)

def require_available(records):
    if type(records) is not tuple or len(records)!=COUNT:raise ValueError('incomplete observation')
    return records
