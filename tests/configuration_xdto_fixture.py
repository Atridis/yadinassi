"""Authored application envelope around exact native package/module inputs."""
from pathlib import Path
from configuration_runtime_fixture import module_files
ROOT=Path(__file__).resolve().parents[1]

def files(linked=False):
    folder=ROOT/'scripts'/('configuration_xdto_linked_behavior' if linked else 'configuration_xdto_behavior')
    source=module_files()
    names=('OwnedRecords','OwnedEnvelope') if linked else ('OwnedRecords',)
    declarations=''.join('<XDTOPackage>'+n+'</XDTOPackage>' for n in names)+'<CommonModule>OwnedXDTOBridge</CommonModule>'
    source['Configuration.xml']=source['Configuration.xml'].replace(b'</ChildObjects>',declarations.encode()+b'</ChildObjects>')
    for name in names:
        source[f'XDTOPackages/{name}.xml']=(folder/(name+'.xml')).read_bytes()
        source[f'XDTOPackages/{name}/Ext/Package.bin']=(folder/('Envelope.bin' if name=='OwnedEnvelope' else 'Package.bin')).read_bytes()
    source['CommonModules/OwnedXDTOBridge.xml']=(folder/'OwnedXDTOBridge.xml').read_bytes()
    source['CommonModules/OwnedXDTOBridge/Ext/Module.bsl']=(folder/'Module.bsl').read_bytes()
    return source
