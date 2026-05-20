from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any

from sim_engine import _line_col


def try_real_pin_run(
    code: str,
    run_id: str,
    pin_root: str
) -> Optional[Dict[str, Any]]:

    # ---------------------------------------------------
    # Resolve Pin binary
    # ---------------------------------------------------

    pin_root_p = Path(pin_root).expanduser().resolve()

    pin_bin = pin_root_p / "pin"

    print("PIN ROOT:", pin_root_p)
    print("PIN BIN:", pin_bin)
    print("PIN EXISTS:", pin_bin.exists())

    if not pin_bin.exists():
        print("Pin binary missing")
        return None

    # ---------------------------------------------------
    # Resolve Pintool
    # ---------------------------------------------------

    tool_lib_env = os.environ.get("PIN_TOOL_LIB")

    print("PIN_TOOL_LIB ENV:", tool_lib_env)

    if not tool_lib_env:
        print("PIN_TOOL_LIB not set")
        return None

    tool_lib = Path(tool_lib_env).expanduser().resolve()

    print("TOOL PATH:", tool_lib)
    print("TOOL EXISTS:", tool_lib.exists())

    if not tool_lib.exists():
        print("Pintool missing")
        return None

    # ---------------------------------------------------
    # Compiler
    # ---------------------------------------------------

    cc = os.environ.get("CC", "gcc")

    print("Compiler:", cc)
    print("Compiler exists:", shutil.which(cc))

    if shutil.which(cc) is None:
        print("Compiler not found")
        return None

    # ---------------------------------------------------
    # Temp workspace
    # ---------------------------------------------------

    work = Path(tempfile.mkdtemp(prefix=f"pinrun_{run_id}_"))

    print("WORK DIR:", work)

    src = work / "main.c"
    exe = work / "main.out"

    src.write_text(code)

    # ---------------------------------------------------
    # Compile target
    # ---------------------------------------------------

    compile_cmd = [
    cc,
    "-O0",
    "-g",
    "-fno-builtin",
    "-fno-builtin-malloc",
    "-fno-builtin-free",
    "-fno-builtin-calloc",
    "-fno-builtin-realloc",
    "-no-pie",
    str(src),
    "-o",
    str(exe),
]

    print("COMPILE CMD:", compile_cmd)

    try:
        cp = subprocess.run(
            compile_cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return {
            "stderr": "Compilation timed out",
            "stdout": "",
            "events": [],
            "markers": [],
            "per_callsite": [],
            "leaks": [],
            "stats": {},
            "memtrace_out": "",
        }

    print("COMPILE RETURN:", cp.returncode)
    print("COMPILE STDOUT:", cp.stdout)
    print("COMPILE STDERR:", cp.stderr)

    if cp.returncode != 0:
        return {
            "stderr": cp.stderr,
            "stdout": cp.stdout,
            "events": [],
            "markers": [],
            "per_callsite": [],
            "leaks": [],
            "stats": {},
            "memtrace_out": "",
        }

    # ---------------------------------------------------
    # Run under Pin
    # ---------------------------------------------------

    out_file = work / "memtrace.out"

    pin_cmd = [
        str(pin_bin),
        "-t",
        str(tool_lib),
        "--",
        str(exe),
    ]

    print("PIN CMD:", pin_cmd)

    try:
        rp = subprocess.run(
            pin_cmd,
            cwd=str(work),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return {
            "stderr": "Pin execution timed out",
            "stdout": "",
            "events": [],
            "markers": [],
            "per_callsite": [],
            "leaks": [],
            "stats": {},
            "memtrace_out": "",
        }

    print("PIN RETURN:", rp.returncode)
    print("PIN STDOUT:", rp.stdout)
    print("PIN STDERR:", rp.stderr)

    memtrace_text = ""

    if out_file.exists():
        memtrace_text = out_file.read_text(errors="ignore")

    print("MEMTRACE SIZE:", len(memtrace_text))
    print(memtrace_text)
    parsed = _parse_memtrace_text(memtrace_text, code)

    parsed["stdout"] = rp.stdout
    parsed["stderr"] = rp.stderr

    return parsed


# =========================================================
# Regexes
# =========================================================

DOUBLE_FREE_RE = re.compile(
    r"DOUBLEFREE\s+"
    r"(?P<addr>0x[0-9a-fA-F]+)"
)

ALLOC_RE = re.compile(
    r"(MALLOC|CALLOC|REALLOC)\s+"
    r"(?P<addr>0x[0-9a-fA-F]+)\s+"
    r"size=(?P<size>\d+)"
)

FREE_RE = re.compile(
    r"FREE\s+"
    r"(?P<addr>0x[0-9a-fA-F]+)"
)

LEAK_RE = re.compile(
    r"LEAK\s+"
    r"(?P<addr>0x[0-9a-fA-F]+)\s+"
    r"size=(?P<size>\d+)"
)


# =========================================================
# Parser
# =========================================================

def _parse_memtrace_text(
    text: str,
    code: str
) -> Dict[str, Any]:

    events = []
    leaks = []
    markers = []

    active_allocs = {}

    timestamp = 0

    # ---------------------------------------------------
    # Parse line-by-line
    # ---------------------------------------------------

    for line in text.splitlines():

        # ---------------- allocations ----------------

        am = ALLOC_RE.search(line)

        if am:

            op = am.group(1).lower()

            ev = {
                "op": op,
                "address": am.group("addr"),
                "size": int(am.group("size")),
                "leaked": False,
                "timestamp_ms": timestamp,
            }

            events.append(ev)

            active_allocs[ev["address"]] = ev

            timestamp += 1

            continue

        # ---------------- frees ----------------

        fm = FREE_RE.search(line)

        if fm:

            addr = fm.group("addr")

            events.append({
                "op": "free",
                "address": addr,
                "size": 0,
                "leaked": False,
                "timestamp_ms": timestamp,
            })

            timestamp += 1

            if addr in active_allocs:
                del active_allocs[addr]

            continue
            df = DOUBLE_FREE_RE.search(line)

        if df:

            addr = df.group("addr")

            markers.append({
                "line": 1,
                "col": 1,
                "end_line": 1,
                "end_col": 5,
                "severity": "warning",
                "message": f"Double free detected at {addr}",
                "size": 0,
                "address": addr,
                "caller_ip": "0x0",
            })

            events.append({
                "op": "doublefree",
                "line": 0,
                "address": addr,
                "size": 0,
                "caller_ip": "0x0",
                "leaked": False,
                "timestamp_ms": timestamp,
            })

            timestamp += 1

            continue

    # ---------------------------------------------------
    # Remaining allocations = leaks
    # ---------------------------------------------------

    for addr, ev in active_allocs.items():

        leak = {
            "address": addr,
            "size": ev["size"],
            "var": "",
            "op": ev["op"],
        }

        leaks.append(leak)

        ev["leaked"] = True

        markers.append({
            "col": 1,
            "end_line": 1,
            "end_col": 5,
            "severity": "error",
            "message": f"Memory leak: {ev['size']} bytes",
            "size": ev["size"],
            "address": addr,
        })

    # ---------------------------------------------------
    # Per-callsite
    # ---------------------------------------------------

    grouped = {}

    for ev in events:

        if ev["op"] == "free":
            continue

        key = ev["caller_ip"]

        if key not in grouped:
            grouped[key] = {
                "calls": 0,
                "total_size": 0,
            }

        grouped[key]["calls"] += 1
        grouped[key]["total_size"] += ev["size"]

    per_callsite = list(grouped.values())

    # ---------------------------------------------------
    # Stats
    # ---------------------------------------------------

    total_calls = sum(
        1 for e in events
        if e["op"] != "free"
    )

    total_bytes = sum(
        e["size"] for e in events
        if e["op"] != "free"
    )

    leaked_bytes = sum(
        l["size"] for l in leaks
    )

    return {
        "memtrace_out": text,
        "events": events,
        "markers": markers,
        "per_callsite": per_callsite,
        "leaks": leaks,
        "stats": {
            "total_calls": total_calls,
            "total_bytes": total_bytes,
            "leaked_bytes": leaked_bytes,
            "leak_count": len(leaks),
            "free_count": sum(
                1 for e in events
                if e["op"] == "free"
            ),
            "active_at_exit": len(leaks),
        },
    }