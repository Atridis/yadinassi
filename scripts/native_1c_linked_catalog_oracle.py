#!/usr/bin/env python3
"""Closed linked-card entrypoint on the existing reviewed host lifecycle."""
from pathlib import Path
import native_1c_catalog_read_oracle as host
import linked_card_inputs
import linked_card_report


def main(argv=None):
    # Source-owned specialization, never caller path/script/database selectors.
    # Restore imported host state so ordinary catalog route stays independent.
    previous=(host.inputs,host.policy,host.OUTPUT,host.container_command)
    def container_command(staged,name,nonce):
        command=previous[3](staged,name,nonce)
        source='/oracle/catalog_read_run.py'
        host.require(command.count(source)==1,'invalid_input')
        command[command.index(source)]='/oracle/linked_card_run.py'
        return command
    try:
        host.inputs=linked_card_inputs;host.policy=linked_card_report
        host.OUTPUT=Path('native-linked-catalog/linked-card.json')
        host.container_command=container_command
        return host.main(argv)
    finally:
        host.inputs,host.policy,host.OUTPUT,host.container_command=previous


if __name__=='__main__':raise SystemExit(main())
