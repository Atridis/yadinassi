#!/usr/bin/env python3
"""Closed document-read entrypoint on the existing reviewed host lifecycle."""
from pathlib import Path
import native_1c_catalog_read_oracle as host
import document_read_inputs
import document_read_report


def main(argv=None):
    # Source-owned specialization, never caller path/script/database selectors.
    # Restore imported host state so ordinary catalog route stays independent.
    previous=(host.inputs,host.policy,host.OUTPUT,host.container_command)
    def container_command(staged,name,nonce):
        command=previous[3](staged,name,nonce)
        source='/oracle/catalog_read_run.py'
        host.require(command.count(source)==1,'invalid_input')
        command[command.index(source)]='/oracle/document_read_run.py'
        return command
    try:
        host.inputs=document_read_inputs;host.policy=document_read_report
        host.OUTPUT=Path('native-document-read/document-read.json')
        host.container_command=container_command
        return host.main(argv)
    finally:
        host.inputs,host.policy,host.OUTPUT,host.container_command=previous


if __name__=='__main__':raise SystemExit(main())
