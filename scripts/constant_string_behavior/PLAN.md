# Owned String(10) Variable observation: NOT EXECUTED

This revision changes only the declared length from the successfully measured
String64 packet to String10 Variable. The marker is now owned-v2 (8 characters),
so no truncation/overflow behavior is being tested or assumed. Source hashes and
packet identity are updated. The same fresh disposable DB and nonce/source/
module/config/cleanup guards remain unchanged; no other scalar types are added.

Earlier String64 success: run43309356636, sourcef3cd1ca0925a22baa4c9ef6ceedbaedeba174223.
That evidence does not prove this new length10 packet. Read first Get, Set, Get
statuses and resulting type/length/equality only after this packet's own run.
Twenty offline tests:8 packet and12 reviewed-push admission. No default inferred
from XML alone; no claim about fixed strings, other lengths or other types.
