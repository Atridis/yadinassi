#!/usr/bin/env python3
"""Explicit, independent opt-in: synthetic file-DB oracle, finite observations only.

No caller-supplied database/config/dump and no legacy full-suite flags are accepted.
Native artifacts, logs and XML never leave the disposable container tmpfs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
import uuid

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
HELPERS=ROOT/'scripts/native_1c_db_oracle'
sys.path.insert(0,str(HELPERS))
sys.path.insert(0,str(ROOT/'yadinassi/storage'))
from protocol import (CHECKS, IMAGE, MAX_REPORT_BYTES, STAGES, decode,
    encode, require)
from comparison import empty_report, validate_report, discard_capture
from snapshots import OracleError
from inputs import inventory, source_hashes, stage_inputs, staged_hashes
import native_1c_smoke as smoke

MAX_RUNTIME=2400
OUTPUT=Path('native-db-oracle/report.json')
REFERENCE_OUTPUTS = {case: OUTPUT.parent / (case + '.json') for case in ('distinct_a','distinct_b')}
REFERENCE_AGGREGATE = OUTPUT.parent / 'reference-aggregate.json'
CODEC_OUTPUTS = {case: OUTPUT.parent / ('codec_' + case + '.json') for case in ('distinct_a','distinct_b')}
CODEC_AGGREGATE = OUTPUT.parent / 'codec-aggregate.json'
ROWS_OUTPUTS = {case: OUTPUT.parent / ('rows_' + case + '.json') for case in ('distinct_a','distinct_b')}
ROWS_AGGREGATE = OUTPUT.parent / 'rows-aggregate.json'
DESCRIPTION_OUTPUTS = {case: OUTPUT.parent / (case+'.json') for case in ('description8','description17')}
DESCRIPTION_AGGREGATE = OUTPUT.parent / 'description-aggregate.json'
DESCRIPTION_ROWS_OUTPUTS = {case: OUTPUT.parent / ('description_rows'+case.removeprefix('description')+'.json') for case in ('description8','description17')}
DESCRIPTION_ROWS_AGGREGATE = OUTPUT.parent / 'description-rows-aggregate.json'
PARAMS_SLOT_OUTPUTS = {case: OUTPUT.parent / ('params_slots'+case.removeprefix('description')+'.json') for case in ('description8','description17')}
PARAMS_SLOT_AGGREGATE = OUTPUT.parent / 'params-slots-aggregate.json'
NUMERIC_CODE_OUTPUTS = {case: OUTPUT.parent / ('numeric_code'+case.removeprefix('number')+'.json') for case in ('number3','number6')}
NUMERIC_CODE_AGGREGATE = OUTPUT.parent / 'numeric-code-aggregate.json'


def provenance(*, record_metadata=False, record_reader=False, params_transport=False, params_extraction=False, dbnames_identity=False, config_transport=False, config_framing=False, config_marker_census=False, config_zero_marker_filename=False, config_entry_reference=False, config_blob_chain=False, config_content_decode=False, config_root_reference_projection=False, config_catalog_observation=False, config_catalog_name_binding=False, config_catalog_standard_binding=False, config_catalog_identity_binding=False, config_catalog_field_matrix=False, config_catalog_attribute_binding=False, catalog_readonly_binding=False, reference_case=None, reference_codec=False, reference_rows=False, description_case=None, description_rows=False, params_slots=False, numeric_case=None):
    inventory(record_metadata,record_reader=record_reader,params_transport=params_transport,params_extraction=params_extraction,dbnames_identity=dbnames_identity,config_transport=config_transport,config_framing=config_framing,config_marker_census=config_marker_census,config_zero_marker_filename=config_zero_marker_filename,config_entry_reference=config_entry_reference,config_blob_chain=config_blob_chain,config_content_decode=config_content_decode,config_root_reference_projection=config_root_reference_projection,config_catalog_observation=config_catalog_observation,config_catalog_name_binding=config_catalog_name_binding,config_catalog_standard_binding=config_catalog_standard_binding,config_catalog_identity_binding=config_catalog_identity_binding,config_catalog_field_matrix=config_catalog_field_matrix,config_catalog_attribute_binding=config_catalog_attribute_binding,catalog_readonly_binding=catalog_readonly_binding,reference_case=reference_case,reference_codec=reference_codec,reference_rows=reference_rows,description_case=description_case,description_rows=description_rows,params_slots=params_slots,numeric_case=numeric_case)
    try:
        repository=smoke.FULL.repository_provenance(ROOT)
    except (smoke.FULL.FullError,OSError):
        raise OracleError('provenance_mismatch') from None
    return {'commit':repository['commit'],'tree':repository['tree'],
        'sources':source_hashes(ROOT,record_metadata=record_metadata,record_reader=record_reader,params_transport=params_transport,params_extraction=params_extraction,dbnames_identity=dbnames_identity,config_transport=config_transport,config_framing=config_framing,config_marker_census=config_marker_census,config_zero_marker_filename=config_zero_marker_filename,config_entry_reference=config_entry_reference,config_blob_chain=config_blob_chain,config_content_decode=config_content_decode,config_root_reference_projection=config_root_reference_projection,config_catalog_observation=config_catalog_observation,config_catalog_name_binding=config_catalog_name_binding,config_catalog_standard_binding=config_catalog_standard_binding,config_catalog_identity_binding=config_catalog_identity_binding,config_catalog_field_matrix=config_catalog_field_matrix,config_catalog_attribute_binding=config_catalog_attribute_binding,catalog_readonly_binding=catalog_readonly_binding,reference_case=reference_case,reference_codec=reference_codec,reference_rows=reference_rows,description_case=description_case,description_rows=description_rows,params_slots=params_slots,numeric_case=numeric_case),
        'image':IMAGE,'platform':'linux/amd64','actual_version':None,'locale':'ru_RU.UTF-8','timezone':'Etc/UTC'}


def container_command(staged,name,nonce, *, record_metadata=False, record_reader=False, params_transport=False, params_extraction=False, dbnames_identity=False, config_transport=False, config_framing=False, config_marker_census=False, config_zero_marker_filename=False, config_entry_reference=False, config_blob_chain=False, config_content_decode=False, config_root_reference_projection=False, config_catalog_observation=False, config_catalog_name_binding=False, config_catalog_standard_binding=False, config_catalog_identity_binding=False, config_catalog_field_matrix=False, config_catalog_attribute_binding=False, catalog_readonly_binding=False, reference_case=None, reference_codec=False, reference_rows=False, description_case=None, description_rows=False, params_slots=False, numeric_case=None):
    require(type(name) is str and re.fullmatch('onec-db-oracle-[0-9a-f]{32}',name) is not None,'invalid_input')
    require(type(nonce) is str and re.fullmatch('[0-9a-f]{32}',nonce) is not None,'invalid_input')
    require(staged.is_dir() and not staged.is_symlink() and ',' not in str(staged),'invalid_input')
    staged_hashes(staged,record_metadata=record_metadata,record_reader=record_reader,params_transport=params_transport,params_extraction=params_extraction,dbnames_identity=dbnames_identity,config_transport=config_transport,config_framing=config_framing,config_marker_census=config_marker_census,config_zero_marker_filename=config_zero_marker_filename,config_entry_reference=config_entry_reference,config_blob_chain=config_blob_chain,config_content_decode=config_content_decode,config_root_reference_projection=config_root_reference_projection,config_catalog_observation=config_catalog_observation,config_catalog_name_binding=config_catalog_name_binding,config_catalog_standard_binding=config_catalog_standard_binding,config_catalog_identity_binding=config_catalog_identity_binding,config_catalog_field_matrix=config_catalog_field_matrix,config_catalog_attribute_binding=config_catalog_attribute_binding,catalog_readonly_binding=catalog_readonly_binding,reference_case=reference_case,reference_codec=reference_codec,reference_rows=reference_rows,description_case=description_case,description_rows=description_rows,params_slots=params_slots,numeric_case=numeric_case)
    return ['docker','run','--name',name,'--hostname','onec-db-oracle',
        '--pull','never','--platform','linux/amd64','--network','none',
        '--user','1000:1000','--read-only','--no-healthcheck','--cap-drop','ALL',
        '--security-opt','no-new-privileges:true','--pids-limit','256',
        '--memory','2g','--memory-swap','2g','--cpus','2',
        '--ulimit','nofile=1024:1024','--ulimit','fsize=67108864:67108864',
        '--ipc','private','--shm-size','128m','--log-driver','none','--stop-timeout','10','--init',
        '--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=1g,mode=1777',
        '--mount',f'type=bind,src={staged.resolve()},dst=/oracle,readonly',
        '--workdir','/tmp','--entrypoint','/usr/bin/env',IMAGE,'-i',
        'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
        'HOME=/tmp/onec-db-oracle/home','TMPDIR=/tmp/onec-db-oracle/temp','XDG_RUNTIME_DIR=/tmp/runtime','DISPLAY=:99',
        'LANG=ru_RU.UTF-8','LC_ALL=ru_RU.UTF-8','TZ=Etc/UTC',
        '/bin/bash','--noprofile','--norc','/oracle/probe.sh','--invocation-nonce',nonce] + (
        ['--catalog-numeric-code-'+numeric_case.removeprefix('number')] if numeric_case is not None else
        ['--catalog-params-slots-'+description_case.removeprefix('description')] if params_slots else
        ['--catalog-description-'+('rows-' if description_rows else '')+description_case.removeprefix('description')] if description_case is not None else
        ['--catalog-reference-'+('rows-' if reference_rows else 'codec-' if reference_codec else '')+reference_case.replace('_','-')] if reference_case is not None else
        ['--catalog-readonly-binding'] if catalog_readonly_binding else
        ['--config-catalog-attribute-binding'] if config_catalog_attribute_binding else
        ['--config-catalog-field-matrix'] if config_catalog_field_matrix else
        ['--config-catalog-identity-binding'] if config_catalog_identity_binding else
        ['--config-catalog-standard-binding'] if config_catalog_standard_binding else
        ['--config-catalog-name-binding'] if config_catalog_name_binding else
        ['--config-catalog-reference-observation'] if config_catalog_observation else
        ['--config-root-reference-projection-observation'] if config_root_reference_projection else
        ['--config-content-decode-observation'] if config_content_decode else
        ['--config-blob-chain-observation'] if config_blob_chain else
        ['--config-entry-reference-observation'] if config_entry_reference else
        ['--config-zero-marker-filename-observation'] if config_zero_marker_filename else
        ['--config-slot-marker-observation'] if config_marker_census else
        ['--config-framing-observation'] if config_framing else
        ['--config-transport-observation'] if config_transport else
        ['--dbnames-identity-validation'] if dbnames_identity else
        ['--params-dbnames-extraction'] if params_extraction else
        ['--params-transport-observation'] if params_transport else
        ['--record-reader-validation'] if record_reader else
        ['--record-metadata-observation'] if record_metadata else [])


def fail_report(report,kind,stage='preflight',*,preserve_primary=False,record_reader=False):
    require(type(record_reader) is bool,'invalid_input')
    report.pop('rejected_basename',None)
    report.pop('failure_context',None)
    # Cleanup has its own checks; do not erase a validated primary failure.
    preserve=(preserve_primary and stage=='cleanup' and kind=='cleanup_unverified'
              and report['status']=='failed' and report['failed_stage']!='cleanup')
    if not preserve:
        report.update(status='failed',failed_stage=stage,failure_kind=kind,accepted=False)
    entry=report['stages'][STAGES.index(stage)]
    entry['status']='failed'
    entry['checks']=({key:report['cleanup'][key] for key in CHECKS[stage]} if stage=='cleanup'
                     else {key:False for key in CHECKS[stage]})
    report['artifacts']=[]
    if report.get('schema') == 59:
        import catalog_numeric_code_policy
        catalog_numeric_code_policy.discard_capture(report,final=True)
    elif report.get('schema') == 56:
        import params_slot_policy
        params_slot_policy.discard_capture(report,final=True)
    elif report.get('schema') == 53:
        import catalog_description_rows
        catalog_description_rows.discard_capture(report,final=True)
    elif report.get('schema') == 50:
        import catalog_description_policy
        catalog_description_policy.discard_capture(report,final=True)
    elif report.get('schema') == 45:
        import catalog_reference_rows as reference_policy
        reference_policy.discard_capture(report,final=True)
    elif report.get('schema') == 42:
        import catalog_reference_codec as reference_policy
        reference_policy.discard_capture(report,final=True)
    elif report.get('schema') == 39:
        import catalog_reference_identity as reference_policy
        reference_policy.discard_capture(report,final=True)
    elif report.get('schema') == 37:
        import catalog_readonly_binding as binding_policy
        binding_policy.discard_capture(report,final=True)
    elif report.get('schema') == 35:
        import config_catalog_attribute_binding as attribute_policy
        attribute_policy.discard_capture(report,final=True)
    elif report.get('schema') == 33:
        import config_catalog_field_matrix as matrix_policy
        matrix_policy.discard_capture(report,final=True)
    elif report.get('schema') == 31:
        import config_catalog_identity_binding
        config_catalog_identity_binding.discard_capture(report,final=True)
    elif report.get('schema') == 29:
        import config_catalog_standard_binding
        config_catalog_standard_binding.discard_capture(report,final=True)
    elif report.get('schema') == 27:
        import config_catalog_name_binding
        config_catalog_name_binding.discard_capture(report,final=True)
    elif report.get('schema') == 25:
        import config_catalog_observation
        config_catalog_observation.discard_capture(report,final=True)
    elif report.get('schema') == 23:
        import config_root_reference_projection
        config_root_reference_projection.discard_capture(report,final=True)
    elif report.get('schema') == 17:
        import config_content_decode
        config_content_decode.discard_capture(report,final=True)
    elif report.get('schema') == 15:
        import config_blob_chain
        config_blob_chain.discard_capture(report,final=True)
    elif report.get('schema') == 14:
        import config_entry_reference
        config_entry_reference.discard_capture(report,final=True)
    elif report.get('schema') == 13:
        import config_zero_marker_filename
        config_zero_marker_filename.discard_capture(report,final=True)
    elif report.get('schema') == 12:
        import config_marker_census
        config_marker_census.discard_capture(report,final=True)
    elif report.get('schema') == 11:
        import config_framing
        config_framing.discard_capture(report,final=True)
    elif report.get('schema') == 10:
        import config_observation
        config_observation.discard_capture(report,final=True)
    elif report.get('schema') == 9:
        import dbnames_identity as identity_policy
        identity_policy.discard_capture(report,final=True)
    elif report.get('schema') == 8:
        import params_extraction
        params_extraction.discard_capture(report,final=True)
    elif report.get('schema') == 7:
        import params_observation
        params_observation.discard_capture(report,final=True)
    elif record_reader:
        import record_validation
        record_validation.discard_capture(report,final=True)
    elif report.get('schema') == 5:
        import record_observation
        record_observation.discard_capture(report)
    else:
        discard_capture(report)


def run_oracle(temp_root, *, record_metadata=False, record_reader=False, params_transport=False, params_extraction=False, dbnames_identity=False, config_transport=False, config_framing=False, config_marker_census=False, config_zero_marker_filename=False, config_entry_reference=False, config_blob_chain=False, config_content_decode=False, config_root_reference_projection=False, config_catalog_observation=False, config_catalog_name_binding=False, config_catalog_standard_binding=False, config_catalog_identity_binding=False, config_catalog_field_matrix=False, config_catalog_attribute_binding=False, catalog_readonly_binding=False, reference_case=None, reference_codec=False, reference_rows=False, description_case=None, description_rows=False, params_slots=False, numeric_case=None):
    inventory(record_metadata,record_reader=record_reader,params_transport=params_transport,params_extraction=params_extraction,dbnames_identity=dbnames_identity,config_transport=config_transport,config_framing=config_framing,config_marker_census=config_marker_census,config_zero_marker_filename=config_zero_marker_filename,config_entry_reference=config_entry_reference,config_blob_chain=config_blob_chain,config_content_decode=config_content_decode,config_root_reference_projection=config_root_reference_projection,config_catalog_observation=config_catalog_observation,config_catalog_name_binding=config_catalog_name_binding,config_catalog_standard_binding=config_catalog_standard_binding,config_catalog_identity_binding=config_catalog_identity_binding,config_catalog_field_matrix=config_catalog_field_matrix,config_catalog_attribute_binding=config_catalog_attribute_binding,catalog_readonly_binding=catalog_readonly_binding,reference_case=reference_case,reference_codec=reference_codec,reference_rows=reference_rows,description_case=description_case,description_rows=description_rows,params_slots=params_slots,numeric_case=numeric_case)
    options=({'reference_case':reference_case,'reference_rows':True} if reference_rows else {'reference_case':reference_case,'reference_codec':True} if reference_codec else {'reference_case':reference_case}) if reference_case is not None else {'catalog_readonly_binding':True} if catalog_readonly_binding else {'config_catalog_attribute_binding':True} if config_catalog_attribute_binding else {'config_catalog_field_matrix':True} if config_catalog_field_matrix else {'config_catalog_identity_binding':True} if config_catalog_identity_binding else {'config_catalog_standard_binding':True} if config_catalog_standard_binding else {'config_catalog_name_binding':True} if config_catalog_name_binding else {'config_catalog_observation':True} if config_catalog_observation else {'config_root_reference_projection':True} if config_root_reference_projection else {'config_content_decode':True} if config_content_decode else {'config_blob_chain':True} if config_blob_chain else {'config_entry_reference':True} if config_entry_reference else {'config_zero_marker_filename':True} if config_zero_marker_filename else {'config_marker_census':True} if config_marker_census else {'config_framing':True} if config_framing else {'config_transport':True} if config_transport else {'dbnames_identity':True} if dbnames_identity else {'params_extraction':True} if params_extraction else {'params_transport':True} if params_transport else {'record_reader':True} if record_reader else {'record_metadata':True} if record_metadata else {}
    if numeric_case is not None:
        import catalog_numeric_code_policy as selected
        options={'numeric_case':numeric_case}
        make_report=lambda nonce, provenance: selected.empty_report(nonce,provenance,numeric_case=numeric_case)
        def check_report(raw, **options):
            value=selected.validate_report(raw, **options)
            require(value['numeric_case']==numeric_case,'provenance_mismatch')
            return value
    elif description_case is not None:
        options=({'description_case':description_case,'params_slots':True} if params_slots else {'description_case':description_case,'description_rows':True} if description_rows else {'description_case':description_case})
        if params_slots:
            import params_slot_policy as selected
        elif description_rows:
            import catalog_description_rows as selected
        else:
            import catalog_description_policy as selected
        make_report=lambda nonce, provenance: selected.empty_report(nonce,provenance,description_case=description_case)
        def check_report(raw, **options):
            value=selected.validate_report(raw, **options)
            require(value['description_case']==description_case,'provenance_mismatch')
            return value
    elif reference_case is not None:
        if reference_rows:
            import catalog_reference_rows as selected
        elif reference_codec:
            import catalog_reference_codec as selected
        else:
            import catalog_reference_identity as selected
        make_report=lambda nonce, provenance: selected.empty_report(nonce, provenance, reference_case=reference_case)
        def check_report(raw, **options):
            value=selected.validate_report(raw, **options)
            require(value['reference_case'] == reference_case, 'provenance_mismatch')
            return value
    elif catalog_readonly_binding:
        import catalog_readonly_binding as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    elif config_catalog_attribute_binding:
        import config_catalog_attribute_binding as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    elif config_catalog_field_matrix:
        import config_catalog_field_matrix as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    elif config_catalog_identity_binding:
        import config_catalog_identity_binding as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    elif config_catalog_standard_binding:
        import config_catalog_standard_binding as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    elif config_catalog_name_binding:
        import config_catalog_name_binding as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    elif config_catalog_observation:
        import config_catalog_observation as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    elif config_root_reference_projection:
        import config_root_reference_projection as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    elif config_content_decode:
        import config_content_decode as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    elif config_blob_chain:
        import config_blob_chain as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    elif config_entry_reference:
        import config_entry_reference as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    elif config_zero_marker_filename:
        import config_zero_marker_filename as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    elif config_marker_census:
        import config_marker_census as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    elif config_framing:
        import config_framing as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    elif config_transport:
        import config_observation as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    elif dbnames_identity:
        import dbnames_identity as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    elif params_extraction:
        import params_extraction as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    elif params_transport:
        import params_observation as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    elif record_reader:
        import record_validation as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    elif record_metadata:
        import record_observation as selected
        make_report=selected.empty_report; check_report=selected.validate_report
    else:
        make_report=empty_report; check_report=validate_report
    # Credentials are removed before git, Docker or any other external process.
    token=os.environ.pop('GHCR_TOKEN',''); actor=os.environ.pop('GHCR_USER','')
    nonce=uuid.uuid4().hex; name='onec-db-oracle-'+uuid.uuid4().hex
    identity=provenance(**options); report=make_report(nonce,identity.copy())
    work_name=None; attempted=False; container_removed=True; native_cleanup=False
    primary=None; validated=False
    try:
        with tempfile.TemporaryDirectory(prefix='onec-db-oracle-',dir=temp_root) as work_name:
            work=Path(work_name).resolve(); staged=work/'inputs'
            stage_inputs(ROOT,staged,nonce,identity,**options)
            require(bool(token) and re.fullmatch('[A-Za-z0-9-]{1,39}',actor) is not None,'registry_credentials_missing')
            auth=work/'auth'; auth.mkdir(mode=0o700)
            try:
                smoke.run_silent(['docker','login','ghcr.io','--username',actor,'--password-stdin'],
                    smoke.docker_environment(auth),60,token.encode())
                token=''
                smoke.run_silent(['docker','pull','--platform','linux/amd64',IMAGE],smoke.docker_environment(auth),600)
            finally:
                token=''; shutil.rmtree(auth)
            clean=work/'no-auth'; clean.mkdir(mode=0o700); env=smoke.docker_environment(clean)
            code,value=smoke.bounded_run(['docker','image','inspect','--format',
                '{{.Os}}/{{.Architecture}}|{{len .Config.Volumes}}',IMAGE],env,30,128)
            require(code==0 and value.strip()==b'linux/amd64|0','container_unavailable')
            try:
                attempted=True; container_removed=False
                code,raw=smoke.bounded_run(container_command(staged,name,nonce,**options),env,MAX_RUNTIME,MAX_REPORT_BYTES)
                report=check_report(raw,nonce=nonce,provenance=identity)
                validated=True
                require((code==0)==(report['status']=='ok'),'transport_invalid')
                native_cleanup=all(report['cleanup'][key] for key in ('native_processes_stopped','raw_files_removed'))
            finally:
                try:
                    smoke.run_silent(['docker','rm','--force',name],env,30)
                    code,value=smoke.bounded_run(['docker','ps','--all','--filter',
                        'name=^/'+name+'$','--format','{{.Names}}'],env,30,128)
                    container_removed=code==0 and not value.strip()
                except smoke.SmokeError:
                    container_removed=False
            require(provenance(**options)==identity,'provenance_mismatch')
    except OracleError as error:
        primary=error.kind
    except smoke.SmokeError as error:
        primary='timeout' if 'timeout' in str(error) else 'container_unavailable'
    except BaseException:
        primary='unexpected_failure'
    finally:
        token=''
    private_removed=work_name is not None and not Path(work_name).exists()
    if primary:
        if not validated: report=make_report(nonce,identity.copy())
        fail_report(report,primary,'cleanup' if validated else 'preflight',record_reader=record_reader)
    if not attempted or (container_removed and not validated):
        native_cleanup=True
        report['cleanup'].update(native_processes_stopped=True,raw_files_removed=True)
    report['cleanup'].update(container_removed=container_removed,private_staging_removed=private_removed)
    if not container_removed or not private_removed:
        fail_report(report,'cleanup_unverified','cleanup',preserve_primary=validated,record_reader=record_reader)
    elif not attempted or not validated:
        entry=report['stages'][-1]; entry['status']='ok'; entry['checks']={key:True for key in CHECKS['cleanup']}
    if not all(report['cleanup'].values()):
        report.pop('rejected_basename',None)
        report.pop('failure_context',None)
    report['accepted']=report['status']=='ok' and all(report['cleanup'].values())
    check_report(encode(report),nonce=nonce,provenance=identity,final=True)
    return report


def export_report(raw, root_identity, *, output=OUTPUT):
    """Exclusive descriptor-relative publication after runtime cleanup/validation.

    No fallback to a path-following write: the real CI host is POSIX. Portable
    protocol/orchestration tests do not need to simulate an unsafe export path.
    """
    require(output in (OUTPUT, *REFERENCE_OUTPUTS.values(), REFERENCE_AGGREGATE, *CODEC_OUTPUTS.values(), CODEC_AGGREGATE, *ROWS_OUTPUTS.values(), ROWS_AGGREGATE, *DESCRIPTION_OUTPUTS.values(), DESCRIPTION_AGGREGATE, *DESCRIPTION_ROWS_OUTPUTS.values(), DESCRIPTION_ROWS_AGGREGATE, *PARAMS_SLOT_OUTPUTS.values(), PARAMS_SLOT_AGGREGATE), 'invalid_input')
    require(os.open in os.supports_dir_fd and hasattr(os,'O_NOFOLLOW')
            and hasattr(os,'O_DIRECTORY'),'unsupported_platform_command')
    require(type(raw) is bytes and len(raw)+1<=MAX_REPORT_BYTES,'artifact_limit')
    root_fd=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    parent_fd=None
    try:
        info=os.fstat(root_fd)
        require((info.st_dev,info.st_ino)==root_identity,'provenance_mismatch')
        try: os.mkdir(output.parent.name,0o700,dir_fd=root_fd)
        except FileExistsError: pass
        parent_fd=os.open(output.parent.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=root_fd)
        parent_info=os.fstat(parent_fd)
        target=os.open(output.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent_fd)
        with os.fdopen(target,'wb') as stream:
            stream.write(raw+b'\n'); stream.flush(); os.fsync(stream.fileno())
            written=os.fstat(stream.fileno())
            require(stat.S_ISREG(written.st_mode) and written.st_nlink==1
                    and written.st_size==len(raw)+1,'transport_invalid')
        current=os.stat(output.parent.name,dir_fd=root_fd,follow_symlinks=False)
        require((current.st_dev,current.st_ino)==(parent_info.st_dev,parent_info.st_ino),'provenance_mismatch')
    finally:
        if parent_fd is not None: os.close(parent_fd)
        os.close(root_fd)


def read_reference_a(root_identity, *, reference_codec=False, reference_rows=False):
    """Read exactly the reviewed A artifact, without following path components."""
    require(type(reference_codec) is bool and type(reference_rows) is bool
            and not (reference_codec and reference_rows), 'invalid_input')
    selected = ROWS_OUTPUTS if reference_rows else CODEC_OUTPUTS if reference_codec else REFERENCE_OUTPUTS
    root_fd=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    parent_fd=None
    try:
        info=os.fstat(root_fd)
        require((info.st_dev,info.st_ino)==root_identity,'provenance_mismatch')
        parent_fd=os.open(OUTPUT.parent.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=root_fd)
        require(set(os.listdir(parent_fd)) == {selected['distinct_a'].name}, 'transport_invalid')
        fd=os.open(selected['distinct_a'].name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent_fd)
        with os.fdopen(fd,'rb') as stream:
            before=os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and 0<before.st_size<=MAX_REPORT_BYTES,'transport_invalid')
            raw=stream.read(MAX_REPORT_BYTES+1)
            after=os.fstat(stream.fileno())
            require((before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_size,after.st_mtime_ns,after.st_ctime_ns)
                    and len(raw)==before.st_size,'transport_invalid')
            return raw
    finally:
        if parent_fd is not None: os.close(parent_fd)
        os.close(root_fd)


def validate_reference_a(root_identity, *, reference_codec=False, reference_rows=False):
    require(type(reference_codec) is bool and type(reference_rows) is bool
            and not (reference_codec and reference_rows), 'invalid_input')
    if reference_rows:
        import catalog_reference_rows as reference_policy
    elif reference_codec:
        import catalog_reference_codec as reference_policy
    else:
        import catalog_reference_identity as reference_policy
    expected=os.environ.get('REFERENCE_A_SHA256')
    require(type(expected) is str and re.fullmatch('[0-9a-f]{64}', expected) is not None, 'provenance_mismatch')
    for key in ('RUN_ID','RUN_ATTEMPT'):
        current=os.environ.get('GITHUB_'+key)
        require(type(current) is str and re.fullmatch('[1-9][0-9]{0,19}',current) is not None
                and os.environ.get('REFERENCE_A_'+key)==current, 'provenance_mismatch')
    raw=read_reference_a(root_identity,reference_rows=True) if reference_rows else read_reference_a(root_identity,reference_codec=True) if reference_codec else read_reference_a(root_identity)
    require(hashlib.sha256(raw).hexdigest()==expected, 'provenance_mismatch')
    value=decode(raw)
    current=provenance(reference_case='distinct_b',reference_rows=True) if reference_rows else provenance(reference_case='distinct_b',reference_codec=True) if reference_codec else provenance(reference_case='distinct_b')
    report=reference_policy.validate_report(raw,nonce=value.get('nonce'),provenance=current,final=True)
    require(report['reference_case']=='distinct_a' and report['accepted'] is True, 'provenance_mismatch')
    return raw


def read_description8(root_identity, *, description_rows=False, params_slots=False):
    """Read exactly the reviewed A artifact, without following path components."""
    require(type(description_rows) is bool and type(params_slots) is bool and not(description_rows and params_slots), 'invalid_input')
    selected = PARAMS_SLOT_OUTPUTS if params_slots else DESCRIPTION_ROWS_OUTPUTS if description_rows else DESCRIPTION_OUTPUTS
    root_fd=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    parent_fd=None
    try:
        info=os.fstat(root_fd)
        require((info.st_dev,info.st_ino)==root_identity,'provenance_mismatch')
        parent_fd=os.open(OUTPUT.parent.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=root_fd)
        require(set(os.listdir(parent_fd)) == {selected['description8'].name}, 'transport_invalid')
        fd=os.open(selected['description8'].name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent_fd)
        with os.fdopen(fd,'rb') as stream:
            before=os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and 0<before.st_size<=MAX_REPORT_BYTES,'transport_invalid')
            raw=stream.read(MAX_REPORT_BYTES+1)
            after=os.fstat(stream.fileno())
            require((before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_size,after.st_mtime_ns,after.st_ctime_ns)
                    and len(raw)==before.st_size,'transport_invalid')
            return raw
    finally:
        if parent_fd is not None: os.close(parent_fd)
        os.close(root_fd)


def validate_description8(root_identity, *, description_rows=False, params_slots=False):
    require(type(description_rows) is bool and type(params_slots) is bool and not(description_rows and params_slots), 'invalid_input')
    if params_slots:
        import params_slot_policy as policy
    elif description_rows:
        import catalog_description_rows as policy
    else:
        import catalog_description_policy as policy
    prefix='PARAMS_SLOTS8_' if params_slots else 'DESCRIPTION_ROWS8_' if description_rows else 'DESCRIPTION8_'
    expected=os.environ.get(prefix+'SHA256')
    require(type(expected) is str and re.fullmatch('[0-9a-f]{64}',expected) is not None,'provenance_mismatch')
    for key in ('RUN_ID','RUN_ATTEMPT'):
        current=os.environ.get('GITHUB_'+key)
        require(type(current) is str and re.fullmatch('[1-9][0-9]{0,19}',current) is not None
                and os.environ.get(prefix+key)==current,'provenance_mismatch')
    raw=read_description8(root_identity,params_slots=True) if params_slots else read_description8(root_identity,description_rows=True) if description_rows else read_description8(root_identity)
    require(hashlib.sha256(raw).hexdigest()==expected,'provenance_mismatch')
    value=decode(raw)
    current=provenance(description_case='description17',params_slots=True) if params_slots else provenance(description_case='description17',description_rows=True) if description_rows else provenance(description_case='description17')
    report=policy.validate_report(raw,nonce=value.get('nonce'),provenance=current,final=True)
    require(report['description_case']=='description8' and report['accepted'] is True,'provenance_mismatch')
    return raw


def read_numeric_code3(root_identity):
    """Read exactly the reviewed A artifact, without following path components."""
    selected = NUMERIC_CODE_OUTPUTS
    root_fd=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    parent_fd=None
    try:
        info=os.fstat(root_fd)
        require((info.st_dev,info.st_ino)==root_identity,'provenance_mismatch')
        parent_fd=os.open(OUTPUT.parent.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=root_fd)
        require(set(os.listdir(parent_fd)) == {selected['number3'].name}, 'transport_invalid')
        fd=os.open(selected['number3'].name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent_fd)
        with os.fdopen(fd,'rb') as stream:
            before=os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and 0<before.st_size<=MAX_REPORT_BYTES,'transport_invalid')
            raw=stream.read(MAX_REPORT_BYTES+1)
            after=os.fstat(stream.fileno())
            require((before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_size,after.st_mtime_ns,after.st_ctime_ns)
                    and len(raw)==before.st_size,'transport_invalid')
            return raw
    finally:
        if parent_fd is not None: os.close(parent_fd)
        os.close(root_fd)


def validate_numeric_code3(root_identity):
    import catalog_numeric_code_policy as policy
    prefix='NUMERIC_CODE3_'
    expected=os.environ.get(prefix+'SHA256')
    require(type(expected) is str and re.fullmatch('[0-9a-f]{64}',expected) is not None,'provenance_mismatch')
    for key in ('RUN_ID','RUN_ATTEMPT'):
        current=os.environ.get('GITHUB_'+key)
        require(type(current) is str and re.fullmatch('[1-9][0-9]{0,19}',current) is not None
                and os.environ.get(prefix+key)==current,'provenance_mismatch')
    raw=read_numeric_code3(root_identity)
    require(hashlib.sha256(raw).hexdigest()==expected,'provenance_mismatch')
    value=decode(raw)
    current=provenance(numeric_case='number6')
    report=policy.validate_report(raw,nonce=value.get('nonce'),provenance=current,final=True)
    require(report['numeric_case']=='number3' and report['accepted'] is True,'provenance_mismatch')
    return raw


class Arguments(argparse.ArgumentParser):
    def error(self,message):
        # Do not echo untrusted input values or possible credentials into CI logs.
        self.exit(2,'File-DB oracle rejected: invalid_input\n')


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ['--validate-numeric-code3']:
        try:
            info=ROOT.stat();validate_numeric_code3((info.st_dev,info.st_ino))
            return 0
        except (OracleError,OSError,ValueError):
            return 2
    if argv in (['--validate-description8'], ['--validate-description-rows8'], ['--validate-params-slots8']):
        try:
            info=ROOT.stat(); validate_description8((info.st_dev,info.st_ino),params_slots=True) if argv == ['--validate-params-slots8'] else validate_description8((info.st_dev,info.st_ino),description_rows=True) if argv == ['--validate-description-rows8'] else validate_description8((info.st_dev,info.st_ino))
            return 0
        except BaseException:
            return 1
    if argv in (['--validate-reference-a'], ['--validate-codec-a'], ['--validate-rows-a']):
        try:
            require('GHCR_TOKEN' not in os.environ and 'GHCR_USER' not in os.environ, 'invalid_input')
            info=ROOT.stat()
            if argv == ['--validate-rows-a']:
                validate_reference_a((info.st_dev, info.st_ino),reference_rows=True)
            elif argv == ['--validate-codec-a']:
                validate_reference_a((info.st_dev, info.st_ino),reference_codec=True)
            else:
                validate_reference_a((info.st_dev, info.st_ino))
            print('Reference A handoff validated.')
            return 0
        except BaseException:
            print('Reference A handoff rejected.', file=sys.stderr)
            return 1
    parser=Arguments(description=__doc__,allow_abbrev=False)
    parser.add_argument('--execute-approved-image',action='store_true')
    parser.add_argument('--file-db-oracle',action='store_true')
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--record-metadata-observation',action='store_true',
        help='explicit bounded baseline metadata/declaration observation; not record acceptance')
    modes.add_argument('--record-reader-validation',action='store_true',
        help='explicit bounded owned-record readback and validation')
    modes.add_argument('--catalog-reference-identity',choices=('distinct_a','distinct_b'))
    modes.add_argument('--catalog-reference-codec',choices=('distinct_a','distinct_b'))
    modes.add_argument('--catalog-numeric-code',choices=('number3','number6'))
    modes.add_argument('--catalog-params-slots',choices=('description8','description17'))
    modes.add_argument('--catalog-description-rows',choices=('description8','description17'))
    modes.add_argument('--catalog-description',choices=('description8','description17'))
    modes.add_argument('--catalog-reference-rows',choices=('distinct_a','distinct_b'))
    modes.add_argument('--catalog-readonly-binding',action='store_true',
        help='independently bind owned CONFIG/DBNames/physical schema and read-only records')
    modes.add_argument('--config-catalog-attribute-binding',action='store_true',
        help='bind owned Catalog attribute UUIDs, names and single primitive qualifiers; no record acceptance')
    modes.add_argument('--config-catalog-field-matrix',action='store_true',
        help='bind fixed three-Catalog owned metadata matrix; no generic CRUD support')
    modes.add_argument('--config-catalog-identity-binding',action='store_true',
        help='Bind internal Catalog UUID, declared key and standard fields to owned verified XML')
    modes.add_argument('--config-catalog-standard-binding',action='store_true',
        help='Bind bounded Catalog declared key and standard fields to owned verified XML')
    modes.add_argument('--config-catalog-name-binding',action='store_true',
        help='Bind partial Catalog declared key and Name to owned verified XML')
    modes.add_argument('--config-catalog-reference-observation',action='store_true',
        help='observe one owned CONFIG Catalog declaration reference; no object identity claim')
    modes.add_argument('--config-root-reference-projection-observation',action='store_true',
        help='bounded partial CONFIG root-reference observation; not complete document or applied-state acceptance')
    modes.add_argument('--config-content-decode-observation',action='store_true',
        help='bounded single-part CONFIG content decode; no native byte equivalence or applied state')
    modes.add_argument('--config-blob-chain-observation',action='store_true',
        help='bounded exact CONFIG selected stored-byte chains; no file or content acceptance')
    modes.add_argument('--config-entry-reference-observation',action='store_true',
        help='bounded CONFIG entry-reference prerequisites; no chain or file acceptance')
    modes.add_argument('--config-zero-marker-filename-observation',action='store_true',
        help='bounded zero-marker CONFIG filename fields only; no file identity or framing acceptance')
    modes.add_argument('--config-slot-marker-observation',action='store_true',
        help='diagnostic CONFIG candidate marker counts only; framing is not accepted')
    modes.add_argument('--config-framing-observation',action='store_true',
        help='check one bounded CONFIG framing/filename hypothesis; no extraction or root identity')
    modes.add_argument('--config-transport-observation',action='store_true',
        help='observe bounded CONFIG declarations only; no framing or root identity')
    modes.add_argument('--params-transport-observation',action='store_true',
        help='finite PARAMS declaration capture, not DBNames extraction')
    modes.add_argument('--params-dbnames-extraction',action='store_true',
        help='finite owned PARAMS/DBNames extraction, without native byte equivalence')
    modes.add_argument('--dbnames-identity-validation',action='store_true',
        help='bounded owned DBNames UUID/name comparison, without native byte equivalence')
    parser.add_argument('--output',default=str(OUTPUT))
    args=parser.parse_args(argv)
    numeric_case = args.catalog_numeric_code
    params_slots = args.catalog_params_slots is not None
    description_rows = args.catalog_description_rows is not None
    description_case = args.catalog_params_slots if params_slots else args.catalog_description_rows if description_rows else args.catalog_description
    reference_rows = args.catalog_reference_rows is not None
    reference_codec = args.catalog_reference_codec is not None
    reference_case = args.catalog_reference_rows if reference_rows else args.catalog_reference_codec if reference_codec else args.catalog_reference_identity
    selected_output = (ROWS_OUTPUTS if reference_rows else CODEC_OUTPUTS if reference_codec else REFERENCE_OUTPUTS).get(reference_case, OUTPUT)
    if description_case is not None:
        selected_output=(PARAMS_SLOT_OUTPUTS if params_slots else DESCRIPTION_ROWS_OUTPUTS if description_rows else DESCRIPTION_OUTPUTS)[description_case]
    if numeric_case is not None:
        selected_output=NUMERIC_CODE_OUTPUTS[numeric_case]
    if not args.execute_approved_image or not args.file_db_oracle or args.output!=str(selected_output):
        parser.error('invalid_input')
    output=ROOT/selected_output
    if output.exists() or output.is_symlink() or output.parent.is_symlink():
        parser.error('stale_evidence')
    try:
        root_info=ROOT.stat(); root_identity=(root_info.st_dev,root_info.st_ino)
        options=({'reference_case':reference_case,'reference_rows':True} if reference_rows else {'reference_case':reference_case,'reference_codec':True} if reference_codec else {'reference_case':reference_case} if reference_case is not None else {'catalog_readonly_binding':True} if args.catalog_readonly_binding else {'config_catalog_attribute_binding':True} if args.config_catalog_attribute_binding else {'config_catalog_field_matrix':True} if args.config_catalog_field_matrix else {'config_catalog_identity_binding':True} if args.config_catalog_identity_binding else {'config_catalog_standard_binding':True} if args.config_catalog_standard_binding else {'config_catalog_name_binding':True} if args.config_catalog_name_binding else {'config_catalog_observation':True} if args.config_catalog_reference_observation else
                 {'config_root_reference_projection':True} if args.config_root_reference_projection_observation else
                 {'config_content_decode':True} if args.config_content_decode_observation else
                 {'config_blob_chain':True} if args.config_blob_chain_observation else
                 {'config_entry_reference':True} if args.config_entry_reference_observation else
                 {'config_zero_marker_filename':True} if args.config_zero_marker_filename_observation else
                 {'config_marker_census':True} if args.config_slot_marker_observation else
                 {'config_framing':True} if args.config_framing_observation else
                 {'config_transport':True} if args.config_transport_observation else
                 {'dbnames_identity':True} if args.dbnames_identity_validation else
                 {'params_extraction':True} if args.params_dbnames_extraction else
                 {'params_transport':True} if args.params_transport_observation else
                 {'record_reader':True} if args.record_reader_validation else
                 {'record_metadata':True} if args.record_metadata_observation else {})
        if description_case is not None:
            options=({'description_case':description_case,'params_slots':True} if params_slots else {'description_case':description_case,'description_rows':True} if description_rows else {'description_case':description_case})
        if numeric_case is not None:
            options={'numeric_case':numeric_case}
        prior_numeric = validate_numeric_code3(root_identity) if numeric_case == 'number6' else None
        prior_description = (validate_description8(root_identity,params_slots=True) if params_slots else validate_description8(root_identity,description_rows=True) if description_rows else validate_description8(root_identity)) if description_case == 'description17' else None
        prior_raw = None
        if reference_case == 'distinct_b':
            if reference_rows:
                import catalog_reference_rows as reference_policy
                prior_raw = validate_reference_a(root_identity,reference_rows=True)
            elif reference_codec:
                import catalog_reference_codec as reference_policy
                prior_raw = validate_reference_a(root_identity,reference_codec=True)
            else:
                import catalog_reference_identity as reference_policy
                prior_raw = validate_reference_a(root_identity)
        report=run_oracle(Path(tempfile.gettempdir()),**options)
        raw=encode(report)
        if reference_case is None and description_case is None and numeric_case is None:
            export_report(raw,root_identity)
        else:
            export_report(raw,root_identity,output=selected_output)
        if 'GITHUB_OUTPUT' in os.environ:
            with open(os.environ['GITHUB_OUTPUT'],'a',encoding='ascii') as target:
                target.write('report_ready=true\n')
                if numeric_case == 'number3':
                    target.write('numeric_code_sha256='+hashlib.sha256(raw+b'\n').hexdigest()+'\n')
                if description_case == 'description8':
                    target.write(('params_slots_sha256=' if params_slots else 'description_rows_sha256=' if description_rows else 'description_sha256=')+hashlib.sha256(raw+b'\n').hexdigest()+'\n')
                if reference_case == 'distinct_a':
                    target.write('reference_sha256='+hashlib.sha256(raw+b'\n').hexdigest()+'\n')
        aggregate_agrees = True
        if prior_numeric is not None and report['accepted']:
            import catalog_numeric_code_policy as policy
            reports=(decode(prior_numeric),report)
            hashes=(hashlib.sha256(prior_numeric).hexdigest(),hashlib.sha256(raw+b'\n').hexdigest())
            aggregate=policy.build_aggregate(reports,hashes,
                run_id=int(os.environ.get('GITHUB_RUN_ID','')),run_attempt=int(os.environ.get('GITHUB_RUN_ATTEMPT','')))
            policy.validate_aggregate(encode(aggregate),provenance=report['provenance'],reports=reports,
                report_sha256s=hashes,run_id=int(os.environ.get('GITHUB_RUN_ID','')),run_attempt=int(os.environ.get('GITHUB_RUN_ATTEMPT','')))
            export_report(encode(aggregate),root_identity,output=NUMERIC_CODE_AGGREGATE)
            if 'GITHUB_OUTPUT' in os.environ:
                with open(os.environ['GITHUB_OUTPUT'],'a',encoding='ascii') as target:
                    target.write('aggregate_ready=true\n')
        if prior_description is not None and report['accepted']:
            if params_slots:
                import params_slot_policy as policy
            elif description_rows:
                import catalog_description_rows as policy
            else:
                import catalog_description_policy as policy
            aggregate=policy.build_aggregate((decode(prior_description),report),
                (hashlib.sha256(prior_description).hexdigest(),hashlib.sha256(raw+b'\n').hexdigest()),
                run_id=int(os.environ.get('GITHUB_RUN_ID','')),run_attempt=int(os.environ.get('GITHUB_RUN_ATTEMPT','')))
            policy.validate_aggregate(encode(aggregate),provenance=report['provenance'],
                reports=(decode(prior_description),report),
                report_sha256s=(hashlib.sha256(prior_description).hexdigest(),hashlib.sha256(raw+b'\n').hexdigest()),
                run_id=int(os.environ.get('GITHUB_RUN_ID','')),run_attempt=int(os.environ.get('GITHUB_RUN_ATTEMPT','')))
            export_report(encode(aggregate),root_identity,output=PARAMS_SLOT_AGGREGATE if params_slots else DESCRIPTION_ROWS_AGGREGATE if description_rows else DESCRIPTION_AGGREGATE)
            if 'GITHUB_OUTPUT' in os.environ:
                with open(os.environ['GITHUB_OUTPUT'],'a',encoding='ascii') as target:
                    target.write('aggregate_ready=true\n')
        if prior_raw is not None and report['accepted']:
            aggregate = reference_policy.aggregate_reports(prior_raw, raw+b'\n', provenance=report['provenance'])
            export_report(encode(aggregate), root_identity, output=ROWS_AGGREGATE if reference_rows else CODEC_AGGREGATE if reference_codec else REFERENCE_AGGREGATE)
            aggregate_agrees = aggregate['rows_verified'] if reference_rows else aggregate['codec_verified'] if reference_codec else aggregate['permutations_agree']
            if 'GITHUB_OUTPUT' in os.environ:
                with open(os.environ['GITHUB_OUTPUT'],'a',encoding='ascii') as target:
                    target.write('aggregate_ready=true\n')
        print('File-DB oracle accepted.' if report['accepted'] and aggregate_agrees else 'File-DB oracle failed; see finite report.')
        return 0 if report['accepted'] and aggregate_agrees else 1
    except BaseException:
        print('File-DB oracle failed before validated report export.',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
