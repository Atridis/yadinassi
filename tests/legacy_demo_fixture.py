"""Test-only assembly for immutable demo_*_v1 compatibility grants.

The only historical bytes stored separately are the old Configuration.xml.
Forms/handlers/catalog metadata come from the one canonical examples/demo;
all nineteen SHA256 pins must match before this legacy projection is returned.
This is not another runnable demo directory and does not expand runtime grants.
"""
from hashlib import sha256
from pathlib import Path
import stat

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_ROOT = 'tests/fixtures/legacy_demo_root.xml'
CANONICAL_ROOT = 'examples/demo'
SOURCE_SHA256 = {'Catalogs/ВидыНоменклатуры.xml': '723c973982629b92c183d68b24aef8fde1771b34e649e536749354d7a14cc2d0',
 'Catalogs/ВидыНоменклатуры/Forms/ФормаЭлемента.xml': 'ccf4960ad91cc507a0e8165c973f79d88c9fe5e1773d1bf8fd1bb90584275a28',
 'Catalogs/ВидыНоменклатуры/Forms/ФормаЭлемента/Ext/Form.xml': '3d5d1cdf429fbc5ece392c4bc4df6621c8753f152c8260a1aa5a83557a2a088d',
 'Catalogs/ВидыНоменклатуры/Forms/ФормаЭлемента/Ext/Form/Module.bsl': '1362d0c9ab909625f98648a719e87422dd7665634e2cc2e55ce01517a198f53f',
 'Catalogs/Номенклатура.xml': '6418b0b403932a38b24c75bb5db5496837cef396897225fa0bc5b80f905fa156',
 'Catalogs/Номенклатура/Ext/ObjectModule.bsl': 'b329bc9a92db51032415bc62f779672acff65beb081237105adedab0f16edec9',
 'Catalogs/Номенклатура/Forms/ФормаСписка.xml': 'ce2e8373aab443a70990c7c1a7f1166e2efc45f025952959ae48de4553f474c2',
 'Catalogs/Номенклатура/Forms/ФормаСписка/Ext/Form.xml': '192dcb7c76a5805afdff477c9bc27f1f67149f1aa53be5a0894dcae931c4afc6',
 'Catalogs/Номенклатура/Forms/ФормаСписка/Ext/Form/Module.bsl': 'cedc20b94809fc639f72ee65d180eb5e6dadb647e02a2ed02d85af7dd1533127',
 'Catalogs/Номенклатура/Forms/ФормаЭлемента.xml': '0d55e449ebff7d194f09af8c92dff5fd53c05db17927a0c478dfae9ad9a7dc6e',
 'Catalogs/Номенклатура/Forms/ФормаЭлемента/Ext/Form.xml': 'ba70bc4129509c979033632d305d4866e0e311f5e25322369bdf3998b055add6',
 'Catalogs/Номенклатура/Forms/ФормаЭлемента/Ext/Form/Module.bsl': '86bccc60f288b6d8bec57dd01701b3535a73c297b1a42a97d2f5528f066426e3',
 'Catalogs/Склады.xml': '3f123ebb7eed85b1b845ae8867749e91cde2d6154cd6e8b5da16a74c9658bb3a',
 'Configuration.xml': '348fb96905c8e87e4803ee40fb6de3bca75902c939386346c6872223bec0c719',
 'Ext/ClientApplicationInterface.xml': '407d37fdc9c46dc9ef03573c8241f574c382e329cc9670bf5eba0d529860b16a',
 'Ext/CommandInterface.xml': 'b36fdd6e977f07daa40e5b4efd4bf8ad1c536f08402642df470587600848315a',
 'Ext/HomePageWorkArea.xml': '16188438d96e87c4103ba71fe773543c1b71f3ca98e93476f3174d816672010e',
 'Languages/Русский.xml': 'e0438b24e18c15da067173886270b2a4806aff1ea97031b2211c3f586181cf3c',
 'Subsystems/НормативнаяИнформация.xml': 'e824868068ac9018757c8fea8adbe4eee1c597a82e0fd6d8215c8d2f94858412'}


def legacy_demo_files(root=ROOT):
    root = Path(root)
    result = {}
    for name, expected in SOURCE_SHA256.items():
        path = root / (HISTORICAL_ROOT if name == 'Configuration.xml' else CANONICAL_ROOT + '/' + name)
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 1048576:
            raise ValueError('legacy demo source file refused')
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != expected:
            raise ValueError('legacy demo source hash mismatch')
        result[name] = raw
    return result


def materialize_legacy_demo(destination, root=ROOT):
    """Explicit owned temporary compatibility fixture, never repository output."""
    source = legacy_demo_files(root)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for name, raw in source.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as output:
            output.write(raw)
    return destination
