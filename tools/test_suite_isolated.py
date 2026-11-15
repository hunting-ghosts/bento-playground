"""Run each declared emulator test in a fresh process; require every summary."""
import argparse
import ast
from pathlib import Path
import re
import subprocess
import sys
import time

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--suite", type=Path, required=True)
a = p.parse_args()
suite = a.suite.resolve()
tree = ast.parse(suite.read_text())
# Match the direct script's unittest.main entry point: classes declared after
# it are not reachable in that invocation and cannot be selected by name.
body = []
for node in tree.body:
    if isinstance(node, ast.If) and "__name__" in ast.unparse(node.test) and "__main__" in ast.unparse(node.test):
        break
    body.append(node)
tests = [c.name + "." + f.name for c in body if isinstance(c, ast.ClassDef)
         for f in c.body if isinstance(f, ast.FunctionDef) and f.name.startswith("test_")]
assert tests, "No declared tests found"
started = time.monotonic()
runner = Path(__file__).with_name("run_arm_suite.py")
for name in tests:
    r = subprocess.run([sys.executable, str(runner), str(suite), name],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(r.stdout, flush=True)
    if r.returncode or not re.search(r"Ran 1 test\b", r.stdout) or not r.stdout.rstrip().endswith("OK"):
        raise SystemExit("Incomplete or failed isolated test: " + name)
print("Ran", len(tests), "tests in", round(time.monotonic()-started, 3),
      "s (one fresh process per test)\n\nOK", flush=True)
