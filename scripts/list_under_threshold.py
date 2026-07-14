"""List pre-v0.2-retained files <80% sorted by import count."""
import json
import re
import subprocess
from collections import Counter

with open(".louke/project/specs/v0.2-004-coverage-recovery/coverage-file-classification.json") as f:
    data = json.load(f)

# Find the key dynamically (handle dict iteration order vs in-script variable shadowing).
summary = data["summary"]
under_key = next((k for k in summary if k.startswith("pre_v0.2_retained_under")), None)
print(f"key: {under_key!r}")

failing = summary[under_key] if under_key else []
under_set = set(f["path"] for f in failing)
failing_lookup = {f["path"]: f for f in failing}

result = subprocess.run(
    ["grep", "-rE", "from quantide\\.", "quantide/", "tests/"],
    capture_output=True, text=True,
)
counter = Counter()
for line in result.stdout.split("\n"):
    m = re.search(r"from quantide\.([\w.]+)\s+import", line)
    if m:
        counter[m.group(1)] += 1

v02 = []
for mod, count in counter.most_common(200):
    full_path = "quantide/" + mod.replace(".", "/") + ".py"
    if full_path in under_set:
        v02.append((mod, count, failing_lookup[full_path]))
v02.sort(key=lambda x: -x[1])
print(f"\n{len(v02)} pre-v0.2-retained files <80% (sorted by import count):")
for mod, count, f in v02:
    print(
        f"  imp={count:4d} cov={f['percent_covered']}% stmts={f['num_statements']:4d}  {mod}"
    )
