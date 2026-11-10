"""Explicit maintenance CLI: python -m yadinassi.storage_migration_cli."""
import argparse
import json
import sys
from pathlib import Path
from uuid import UUID
from .catalog_backend import BackendError
from .sqlite_migration_plan import StorageMigrationPlan, prepare, apply, resolve, _validate


def encode_plan(plan):
    _validate(plan)
    return json.dumps({'format':'storage_migration_plan_v1','migration_id':str(plan.migration_id),
        'database_id':str(plan.database_id),'source_version':plan.source_version,'target_version':plan.target_version,
        'source_hash':plan.source_hash,'steps':plan.steps,'plan_hash':plan.plan_hash},sort_keys=True,indent=2)+'\n'


def decode_plan(raw):
    if type(raw) is not str or len(raw.encode('utf-8')) > 65536: raise BackendError('invalid_input')
    try:
        data=json.loads(raw)
        if type(data) is not dict or set(data)!={'format','migration_id','database_id','source_version','target_version','source_hash','steps','plan_hash'} or data['format']!='storage_migration_plan_v1' or type(data['steps']) is not list: raise BackendError('invalid_input')
        plan=StorageMigrationPlan(UUID(data['migration_id']),UUID(data['database_id']),data['source_version'],data['target_version'],data['source_hash'],tuple(data['steps']),data['plan_hash'])
        _validate(plan);return plan
    except (ValueError,TypeError,KeyError): raise BackendError('invalid_input') from None


def main(argv=None):
    parser=argparse.ArgumentParser(description='Explicit offline owned SQLite migration',allow_abbrev=False)
    parser.add_argument('action',choices=('plan','apply','resolve'))
    parser.add_argument('database')
    parser.add_argument('--maintenance',action='store_true',help='Confirm all database processes stopped and an operator backup retained')
    parser.add_argument('--plan-file',required=True,help='New output for plan; saved exact input for apply/resolve')
    args=parser.parse_args(argv)
    if not args.maintenance:parser.error('--maintenance is required; no implicit upgrades')
    try:
        if args.action=='plan':
            plan=prepare(args.database,maintenance=True)
            # Never overwrite an earlier recovery plan.
            with open(args.plan_file,'x',encoding='utf-8',newline='\n') as stream:stream.write(encode_plan(plan))
            print('plan_saved')
        else:
            with open(args.plan_file,encoding='utf-8') as stream:raw=stream.read(65537)
            plan=decode_plan(raw)
            if args.action=='apply':apply(args.database,plan,maintenance=True);print('committed')
            else:print(resolve(args.database,plan,maintenance=True))
        return 0
    except BackendError as error:print(error.code,file=sys.stderr);return 2
    except (OSError,UnicodeError):print('storage_error',file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
