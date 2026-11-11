"""Closed five-flow owned managed form acquisition. No native execution on import."""
from pathlib import Path
import hashlib
import re
ROOT = Path(__file__).resolve().parent
MAX_SOURCE = 16384
MAX_OUTPUT = 8192
COUNT = 5
PACKET_HASHES = {'Launcher/Ext/ObjectModule.bsl': 'ce374bb1fcaa576083528b13c364059bb10cdd833534a73f66719b3fab5995fe', 'Launcher/Forms/Child/Ext/Form/Module.bsl': '7f1ac6e3b60cb51c7531104201381cb1e4ab259d44d85ef4e3b58a028858c60b', 'Launcher/Forms/Child/Ext/Form.xml': '45503999c3eeae185c67c6b1688dbf36b31111b241851841c85c6cbf29893186', 'Launcher/Forms/Child.xml': 'd44eeeb992d1061e2c044efed17b5eef161816c3d16298e770db036c092ae04b', 'Launcher/Forms/Main/Ext/Form/Module.bsl': '1432d3c33bb7955452e66ba0b5af586ac0fe38a7b4839a622976d50987874e1b', 'Launcher/Forms/Main/Ext/Form.xml': '06bb1943fcc9ab460baa9a143717b24e53f14d684ad8023c9f386b7a742d3de5', 'Launcher/Forms/Main.xml': 'b21910e73df0952f79708abe9122615d545e41e498da8a6aa5396594d4ffdcb2', 'Launcher.xml': '5d5eefbcf87fde5acc643e77d2bd6aaf96dd005973f2dfff65a0113f29c35fb7'}
SOURCE_SHA256 = hashlib.sha256(b''.join(p.encode()+b'\0'+bytes.fromhex(h) for p,h in sorted(PACKET_HASHES.items()))).hexdigest()
FORM_SHA256 = hashlib.sha256(b''.join(p.encode()+b'\0'+bytes.fromhex(h) for p,h in sorted(PACKET_HASHES.items()) if p.endswith('.xml'))).hexdigest()
EVENTS = frozenset(('start','open','cancel_open','request_close','before_close','refuse_close','closed','notify','finish'))


def packet():
    values = {}
    for path, expected in PACKET_HASHES.items():
        file = ROOT/path
        if file.is_symlink() or not file.is_file(): raise ValueError('packet file shape')
        raw = file.read_bytes()
        if not 0 < len(raw) <= MAX_SOURCE or hashlib.sha256(raw).hexdigest()!=expected:
            raise ValueError('packet source identity')
        values[path] = raw
    return values


def parse_records(raw):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_OUTPUT: raise ValueError('records size')
    try: text=raw.decode('ascii')
    except UnicodeDecodeError: raise ValueError('records encoding') from None
    parts=text.split('|')
    if len(parts)!=6 or parts[-1]!='': raise ValueError('records inventory')
    result=[]
    for number,part in enumerate(parts[:-1],1):
        match=re.fullmatch(r'FR([1-5])=([01]);(none|string|undefined|structure|other);([01]);([01]);([a-z_,]+)',part)
        if not match or int(match[1])!=number: raise ValueError('record shape')
        calls=int(match[2]);kind=match[3];matches=int(match[4]);seen=int(match[5]);codes=match[6].split(',')
        if codes[-1]!='' or not 2<=len(codes)-1<=16: raise ValueError('trace bound')
        codes=tuple(codes[:-1])
        if any(code not in EVENTS for code in codes) or codes[0]!='start' or codes[-1]!='finish': raise ValueError('trace code')
        if codes.count('start')!=1 or codes.count('finish')!=1 or codes.count('open')!=1 or codes.count('notify')!=calls:
            raise ValueError('trace count')
        if number<5 and (calls!=1 or codes.count('closed')!=1): raise ValueError('incomplete lifecycle')
        if number==5 and codes.count('cancel_open')!=1: raise ValueError('missing cancellation observation')
        if number<5 and 'cancel_open' in codes: raise ValueError('unexpected cancellation')
        if number==4 and (codes.count('refuse_close')!=1 or codes.count('request_close')!=2 or codes.count('before_close')!=2): raise ValueError('missing close-refusal lifecycle')
        if number!=4 and 'refuse_close' in codes: raise ValueError('unexpected close refusal')
        if calls==0 and (kind!='none' or matches!=0 or seen!=0): raise ValueError('absent result')
        result.append((calls,kind,matches,seen,codes))
    return tuple(result)


def require_available(records):
    if type(records) is not tuple or len(records)!=COUNT: raise ValueError('incomplete observation')
    return records
