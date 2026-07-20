!fix.py
import os

# Read raw content
from pathlib import Path
p = Path("backend") / "agent" / "base.py"
with open(p, "rb") as f:
    bytes = f.read()

# Find the AMBIGUOUS_WORDS section
import re
match = re.search(b\"AMBIGUOUS_WORDS.+?\\{\", bytes, re.DOTAL)
if match:
    start = match.start()
    end = bytes.find(b")}", start) + 2
    section = bytes[start:end]
    print("Found section:")
    for i, b in enumerate(section.split(b"\n")):
        print(f"  Length: {len(b)}, hex: {b[:20].hex()}")
