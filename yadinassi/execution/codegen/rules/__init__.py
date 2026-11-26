"""BSL-to-Python lowering rules, organized by the operation they change.

Start with direct_call_rules for exceptional call shapes, and with
direct_scalar_lowering, direct_flow_lowering, or direct_reference_lowering
for scalar operators, control flow, and references respectively. The emitter
combines the rules; runtime operations stay in the parent package.
"""
