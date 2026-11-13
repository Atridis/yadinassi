"""Bounded source TypeSet indirection, never dynamic host type loading.

Only a whole singleton DefinedType TypeSet is expanded. Mixed TypeSet overrides,
unknown type sets and malformed declarations remain explicit unsupported cases.
"""
from .configuration_xml import MD, V8, CFG, _object, _props, _text, _qname


class SourceDefinedTypes:
    def __init__(self, source):
        self.files = {entry.path:entry.content for entry in source.files}
        self.inventory = {entry.path:entry for entry in source.metadata if entry.family == 'DefinedType'}
        obj, _ = _object(self.files['Configuration.xml'], 'Configuration')
        children = obj.find('{' + MD + '}ChildObjects')
        self.names = {}
        self.inventory_error = None
        if children is not None:
            for child in children:
                if child.tag != '{' + MD + '}DefinedType':
                    continue
                name = (child.text or '').strip()
                if child.attrib or len(child) or not name or len(name) > 256 or name.casefold() in self.names:
                    self.inventory_error = 'invalid DefinedType inventory'
                    continue
                self.names[name.casefold()] = name
        if len(self.names) > 1024:
            self.inventory_error = 'DefinedType inventory bound'

    def resolve(self, props, namespaces):
        dependencies = []
        seen = set()
        while True:
            node = props.get('{' + MD + '}Type')
            if node is None:
                raise ValueError('missing defined type declaration')
            aliases = [n for n in node if n.tag == '{' + V8 + '}TypeSet']
            if not aliases:
                return props, namespaces, tuple(dependencies)
            if self.inventory_error:
                raise ValueError(self.inventory_error)
            if (node.attrib or (node.text or '').strip() or len(node) != 1
                    or len(aliases) != 1 or aliases[0].attrib or len(aliases[0])
                    or (aliases[0].tail or '').strip()):
                raise ValueError('mixed or qualified DefinedType TypeSet unsupported')
            namespace, target = _qname(aliases[0], namespaces)
            if namespace != CFG or not target.startswith('DefinedType.'):
                raise ValueError('unsupported source type set')
            key = target[len('DefinedType.'):].casefold()
            if key in seen or len(seen) >= 16:
                raise ValueError('cyclic or excessive DefinedType chain')
            seen.add(key)
            name = self.names.get(key)
            if name is None:
                raise ValueError('unknown DefinedType: ' + target)
            path = 'DefinedTypes/' + name + '.xml'
            item = self.inventory.get(path)
            if item is None or path not in self.files:
                raise ValueError('missing DefinedType source: ' + name)
            obj, namespaces = _object(self.files[path], 'DefinedType')
            props = _props(obj)
            if _text(props, 'Name') != name or str(item.identity) != obj.get('uuid'):
                raise ValueError('DefinedType identity mismatch: ' + name)
            dependencies.append((str(item.identity), name))
