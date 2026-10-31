#!/usr/bin/env python3
"""Read-only reproducible tests for tc check; no board or API writes."""
import contextlib
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('coord_audit', root / 'coord/coord.py')
coord = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coord)

def run(args):
    output = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(output):
        try:
            coord.cmd_tc_check(args)
        except SystemExit as exc:
            code = exc.code
    return code, output.getvalue()

code, output = run(SimpleNamespace(build='AUDIT-NO-RELEASE-SHA'))
print('TEST 1: actual board, non-release build; expected NO-GO')
print(output, end='')
print('exit:', code)
assert code == 1

# Synthetic rows only; they never touch SHARED_BOARD.md. No source files exist.
ids = ['L-03','L-05','L-11','L-20','L-23','L-32','L-33','L-34','L-40','L-47','L-60','R-05-a','Y-07-b','Y-16','Y-24']
rows = [(i, [case, 'synthetic', '-', '✅', 'dummy-sha', '-', '-', '/nonexistent/evidence']) for i, case in enumerate(ids)]
with patch.object(coord, 'load', return_value='ignored'), patch.object(coord, 'get_sec', return_value='ignored'), patch.object(coord, 'table', return_value=([], [], rows)), patch.object(coord.glob, 'glob', return_value=[]):
    code, output = run(SimpleNamespace(build='dummy-sha'))
print('\nTEST 2: mock 15 successes, no source files, nonexistent evidence; expected rejection')
print(output, end='')
print('exit:', code)
if code == 0:
    print('FINDING: false positive reproduced; expected rejection did not occur.')
else:
    print('PASS: invalid input rejected.')
assert code == 0, 'Behavior changed: re-evaluate this finding.'
