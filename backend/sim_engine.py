# """"
# Simulation engine: parses C source code, simulates memory allocations
# (malloc/calloc/realloc/free/aligned_alloc/posix_memalign), and produces
# a memtrace.out style report identical to the Pin tool output, plus
# structured data for the IDE.

# This is intentionally heuristic: it locates allocation/free call sites by
# regex, evaluates simple constant size expressions, and tracks pairing
# between alloc and free using variable-name flow.
# """
from __future__ import annotations
import re
import csv as csv_module
import io
import random
from typing import List, Dict, Any, Tuple, Optional

ALLOC_PATTERN = re.compile(
    r"\b(?P<func>malloc|calloc|realloc|aligned_alloc|_aligned_malloc|posix_memalign)\s*\("
)

FREE_PATTERN = re.compile(
    r"\b(?P<func>free|_aligned_free)\s*\(\s*(?P<arg>[^);,]+?)\s*\)"
)

ASSIGN_PATTERN = re.compile(
    r"(?:^|[\s;{(])"
    r"(?:[\w\[\].>\-*]+\s*=\s*)?"
    r"(?:\([^)]*\)\s*)?"
    r"(?P<func>malloc|calloc|realloc|aligned_alloc|_aligned_malloc|posix_memalign)"
    r"\s*\("
)

def _eval_size_expr(expr: str) -> int:
    """Best-effort evaluation of a size expression. Returns reasonable default if unknown."""

    s = expr.strip()

    # Primitive types
    s = re.sub(r"\bsizeof\s*\(\s*char\s*\)", "1", s)
    s = re.sub(r"\bsizeof\s*\(\s*int\s*\)", "4", s)
    s = re.sub(r"\bsizeof\s*\(\s*long\s*\)", "8", s)
    s = re.sub(r"\bsizeof\s*\(\s*long\s+long\s*\)", "8", s)
    s = re.sub(r"\bsizeof\s*\(\s*short\s*\)", "2", s)
    s = re.sub(r"\bsizeof\s*\(\s*float\s*\)", "4", s)
    s = re.sub(r"\bsizeof\s*\(\s*double\s*\)", "8", s)

    # Pointer types
    s = re.sub(r"\bsizeof\s*\(\s*void\s*\*\s*\)", "8", s)
    s = re.sub(r"\bsizeof\s*\(\s*[A-Za-z_]\w*\s*\*\s*\)", "8", s)

    # Struct/custom types
    s = re.sub(r"\bsizeof\s*\(\s*[A-Za-z_]\w*\s*\)", "16", s)

    # Only arithmetic allowed now
    if not re.fullmatch(r"[\d\s+\-*/()]+", s):
        return 64

    try:
        return max(1, int(eval(s)))
    except Exception:
        return 64

def _split_top_level_args(arg_str: str) -> List[str]:
    """Split call args on top-level commas."""
    parts, depth, cur = [], 0, []
    for ch in arg_str:
        if ch == '(' or ch == '[':
            depth += 1
            cur.append(ch)
        elif ch == ')' or ch == ']':
            depth -= 1
            cur.append(ch)
        elif ch == ',' and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur).strip())
    return parts


def _find_matching_paren(text: str, open_idx: int) -> int:
    depth = 0
    i = open_idx
    while i < len(text):
        c = text[i]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _line_col(text: str, idx: int) -> Tuple[int, int]:
    line = text.count('\n', 0, idx) + 1
    last_nl = text.rfind('\n', 0, idx)
    col = idx - (last_nl + 1) + 1
    return line, col


def _extract_lhs_var(line_text: str) -> Optional[str]:
    m = re.search(
        r"([A-Za-z_]\w*)\s*=\s*(?:\([^)]*\)\s*)?"
        r"(?:malloc|calloc|realloc|aligned_alloc|_aligned_malloc|posix_memalign)\s*\(",
        line_text,
    )
    if m:
        return m.group(1)

    m = re.search(
        r"posix_memalign\s*\(\s*(?:\(?.*?\)?\s*)?&\s*([A-Za-z_]\w*)",
        line_text,
    )
    if m:
        return m.group(1)

    return None


def _is_null_arg(arg: str) -> bool:
    """Return True if the free() argument is NULL / 0 / ((void*)0) etc."""
    cleaned = re.sub(r"\(.*?\)", "", arg).strip()
    return cleaned in ("NULL", "0", "nullptr", "(void*)0", "((void*)0)")


def simulate_pin_run(code: str) -> Dict[str, Any]:
    """Walk the C source, simulate allocation events, return structured result."""
    events: List[Dict[str, Any]] = []
    active: Dict[str, Dict[str, Any]] = {}    # var_name -> alloc_record
    addresses: Dict[str, str] = {}            # var_name -> hex address
    per_callsite: Dict[int, Dict[str, Any]] = {}  # keyed by line_no
    # --- double-free tracking ---
    freed_addresses: Dict[str, int] = {}      # hex_addr -> line_no of first free
    freed_vars: Dict[str, int] = {}           # var_name -> line_no of first free
    double_frees: List[Dict[str, Any]] = []
    # ----------------------------
    rng = random.Random(0xC0FFEE)
    base_addr = 0x55c0a0a00000

    lines = code.splitlines()

    # Walk allocation matches in order
    matches = list(ALLOC_PATTERN.finditer(code))
    timestamp = 0
    for m in matches:
        func = m.group("func")
        open_paren = m.end() - 1
        close_paren = _find_matching_paren(code, open_paren)
        if close_paren == -1:
            continue
        args_raw = code[open_paren + 1:close_paren]
        args = _split_top_level_args(args_raw)

        line_no, _ = _line_col(code, m.start())
        line_text = lines[line_no - 1] if 0 < line_no <= len(lines) else ""

        # Compute alloc size
        size = 0
        if func == "malloc":
            size = _eval_size_expr(args[0]) if args else 0
        elif func == "calloc":
            n = _eval_size_expr(args[0]) if len(args) > 0 else 1
            sz = _eval_size_expr(args[1]) if len(args) > 1 else 1
            size = n * sz
        elif func == "realloc":
            size = _eval_size_expr(args[1]) if len(args) > 1 else 0
        elif func in ("aligned_alloc", "_aligned_malloc"):
            if func == "aligned_alloc":
                size = _eval_size_expr(args[1]) if len(args) > 1 else 0
            else:
                size = _eval_size_expr(args[0]) if args else 0
        elif func == "posix_memalign":
            size = _eval_size_expr(args[2]) if len(args) > 2 else 0

        var = _extract_lhs_var(line_text) or f"anon_{line_no}"
        addr = f"0x{base_addr + rng.randint(0, 0xFFFFFF):x}"
        caller_ip = f"0x{0x400000 + line_no * 0x40:x}"

        # Realloc: free old binding
        if func == "realloc":
            if var in active:
                old = active.pop(var)
                freed_addresses[old["address"]] = line_no
                freed_vars[var] = line_no
                events.append({
                    "op": "free(realloc)", "line": line_no, "address": old["address"],
                    "size": old["size"], "caller_ip": old["caller_ip"], "leaked": False,
                    "timestamp_ms": timestamp,
                })
                timestamp += 1
            else:
                old_var = args[0].strip().lstrip("&") if args else ""
                old_var = re.sub(r"^(\w+).*", r"\1", old_var)
                if old_var and old_var in active:
                    old = active.pop(old_var)
                    freed_addresses[old["address"]] = line_no
                    freed_vars[old_var] = line_no
                    events.append({
                        "op": "free(realloc)", "line": line_no, "address": old["address"],
                        "size": old["size"], "caller_ip": old["caller_ip"], "leaked": False,
                        "timestamp_ms": timestamp,
                    })
                    timestamp += 1

        # A fresh alloc clears any prior double-free record for this var/addr
        freed_vars.pop(var, None)
        freed_addresses.pop(addr, None)

        record = {
            "op": func,
            "line": line_no,
            "address": addr,
            "size": size,
            "caller_ip": caller_ip,
            "leaked": False,
            "timestamp_ms": timestamp,
        }
        events.append(record)
        addresses[var] = addr
        active[var] = dict(record)

        if line_no not in per_callsite:
            per_callsite[line_no] = {"caller_ip": caller_ip, "line": line_no, "total_size": 0, "calls": 0}
        per_callsite[line_no]["total_size"] += size
        per_callsite[line_no]["calls"] += 1
        timestamp += 1

    # Walk frees in order
    for fm in FREE_PATTERN.finditer(code):
        arg = fm.group("arg").strip()
        line_no, _ = _line_col(code, fm.start())

        # ── free(NULL) → report as double-free (per C spec it's a no-op but
        #    many style guides flag it; treat it as an error here per spec)
        if _is_null_arg(arg):
            df_entry = {
                "line": line_no,
                "address": "0x0",
                "var": "NULL",
                "first_free_line": None,   # NULL was never validly allocated
                "kind": "free(NULL)",
            }
            double_frees.append(df_entry)
            events.append({
                "op": "double-free(NULL)", "line": line_no, "address": "0x0",
                "size": 0, "caller_ip": "0x0", "leaked": False,
                "timestamp_ms": timestamp,
            })
            timestamp += 1
            continue

        arg = re.sub(r"^\s*", "", arg)
        arg = re.sub(r"\(.*?\)\s*", "", arg)
        var_m = re.match(r"&?\s*([A-Za-z_]\w*)", arg)
        if not var_m:
            continue
        vname = var_m.group(1)

        if vname in active:
            rec = active.pop(vname)
            addr = rec["address"]

            # Record in freed sets
            freed_vars[vname] = line_no
            freed_addresses[addr] = line_no

            events.append({
                "op": "free", "line": line_no, "address": addr,
                "size": rec["size"], "caller_ip": rec["caller_ip"], "leaked": False,
                "timestamp_ms": timestamp,
            })

        elif vname in freed_vars:
            # ── Double-free: variable was already freed
            first_line = freed_vars[vname]
            addr = addresses.get(vname, "0x?")
            df_entry = {
                "line": line_no,
                "address": addr,
                "var": vname,
                "first_free_line": first_line,
                "kind": "double-free",
            }
            double_frees.append(df_entry)
            events.append({
                "op": "double-free", "line": line_no, "address": addr,
                "size": 0, "caller_ip": "0x0", "leaked": False,
                "timestamp_ms": timestamp,
            })

        else:
            # Unknown pointer — still emit a free(unknown) but check address set too
            addr_guess = addresses.get(vname, "0x0")
            if addr_guess in freed_addresses:
                first_line = freed_addresses[addr_guess]
                df_entry = {
                    "line": line_no,
                    "address": addr_guess,
                    "var": vname,
                    "first_free_line": first_line,
                    "kind": "double-free(alias)",
                }
                double_frees.append(df_entry)
                events.append({
                    "op": "double-free(alias)", "line": line_no, "address": addr_guess,
                    "size": 0, "caller_ip": "0x0", "leaked": False,
                    "timestamp_ms": timestamp,
                })
            else:
                events.append({
                    "op": "free(unknown)", "line": line_no,
                    "address": "0x0", "size": 0, "caller_ip": "0x0",
                    "leaked": False, "timestamp_ms": timestamp,
                })

        timestamp += 1

    # Anything still in `active` is leaked
    leaks = []
    markers = []
    for vname, rec in active.items():
        rec["leaked"] = True
        for ev in events:
            if ev.get("address") == rec["address"] and ev.get("line") == rec["line"]:
                ev["leaked"] = True
        leaks.append({
            "address": rec["address"],
            "size": rec["size"],
            "caller_ip": rec["caller_ip"],
            "line": rec["line"],
            "var": vname,
            "op": rec["op"],
        })
        line_no = rec["line"]
        line_text = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
        markers.append({
            "line": line_no,
            "col": 1,
            "end_line": line_no,
            "end_col": max(1, len(line_text) + 1),
            "severity": "warning",
            "message": (
                f"Memory leak: {rec['size']} bytes allocated by {rec['op']} "
                f"never freed (address {rec['address']})"
            ),
            "size": rec["size"],
            "address": rec["address"],
            "caller_ip": rec["caller_ip"],
        })

    # Add error markers for double-frees
    for df in double_frees:
        line_no = df["line"]
        line_text = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
        if df["kind"] == "free(NULL)":
            msg = f"free(NULL) called at line {line_no} — NULL pointer freed (undefined-behaviour risk)"
        else:
            msg = (
                f"Double-free of '{df['var']}' (address {df['address']}) "
                f"at line {line_no}; first freed at line {df['first_free_line']}"
            )
        markers.append({
            "line": line_no,
            "col": 1,
            "end_line": line_no,
            "end_col": max(1, len(line_text) + 1),
            "severity": "error",
            "message": msg,
            "address": df["address"],
            "caller_ip": "0x0",
            "size": 0,
        })

    total_calls = len([e for e in events if e["op"] in
                       ("malloc", "calloc", "realloc", "aligned_alloc", "_aligned_malloc", "posix_memalign")])
    total_bytes = sum(e["size"] for e in events if e["op"] in
                      ("malloc", "calloc", "realloc", "aligned_alloc", "_aligned_malloc", "posix_memalign"))
    leaked_bytes = sum(l["size"] for l in leaks)

    # Build memtrace.out style text
    lines_out = []
    for ev in events:
        op = ev["op"]
        if op.startswith("double-free"):
            if op == "double-free(NULL)":
                lines_out.append(f"ERROR: free(NULL) at line {ev['line']}\n")
            else:
                lines_out.append(
                    f"ERROR: Double-free at line {ev['line']} "
                    f"address {ev['address']} ({op})\n"
                )
        elif op.startswith("free"):
            if ev["address"] == "0x0":
                lines_out.append("Free:  0x0 (Unknown source)\n")
            else:
                lines_out.append(f"Free:  {ev['address']}\n")
        else:
            lines_out.append(
                f"Memory Allocation address: {ev['address']}\n"
                f"of size = {ev['size']} bytes\n"
                f"Called by Instruction pointer address: {ev['caller_ip']}\n"
                f"Allocator: {ev['op']}\n\n"
            )
    memtrace = "".join(lines_out)
    memtrace += "\nMEMORY INSTRUMENTATION REPORT\n"
    memtrace += f"Total Malloc Calls:     {total_calls}\n"
    memtrace += f"Total Bytes Allocated:  {total_bytes}\n"
    memtrace += "\nAllocations per Call Site\n"
    for cs in per_callsite.values():
        memtrace += f"Caller: {cs['caller_ip']}  Total: {cs['total_size']} bytes  (calls={cs['calls']})\n"
    memtrace += "\nMemory Leaks Detected\n"
    if not leaks:
        memtrace += "No leaks detected\n"
    else:
        for l in leaks:
            memtrace += (f"LEAK: Address {l['address']} | Size: {l['size']} | "
                         f"Allocated by: {l['caller_ip']} | Allocator: {l['op']}\n")
    memtrace += f"Total bytes leaked: {leaked_bytes}\n"
    memtrace += "\nDouble-Free / Invalid-Free Errors\n"
    if not double_frees:
        memtrace += "No double-free errors detected\n"
    else:
        for df in double_frees:
            if df["kind"] == "free(NULL)":
                memtrace += f"FREE(NULL): line {df['line']}\n"
            else:
                memtrace += (
                    f"DOUBLE-FREE ({df['kind']}): var='{df['var']}' "
                    f"address={df['address']} line={df['line']} "
                    f"first_freed_at_line={df['first_free_line']}\n"
                )

    stats = {
        "total_calls": total_calls,
        "total_bytes": total_bytes,
        "leaked_bytes": leaked_bytes,
        "leak_count": len(leaks),
        "free_count": sum(1 for e in events if e["op"].startswith("free")),
        "active_at_exit": len(leaks),
        "double_free_count": len(double_frees),
    }

    return {
        "memtrace_out": memtrace,
        "events": events,
        "markers": markers,
        "per_callsite": list(per_callsite.values()),
        "leaks": leaks,
        "double_frees": double_frees,
        "stats": stats,
        "stdout": "[simulation] program executed successfully",
        "stderr": "",
    }


def build_csv_report(result: Dict[str, Any]) -> str:
    buf = io.StringIO()
    w = csv_module.writer(buf)
    w.writerow(["#", "section", "report"])
    w.writerow(["", "summary", "PinTrace Memory Instrumentation Report"])
    w.writerow([])
    w.writerow(["index", "op", "line", "address", "size_bytes", "caller_ip", "leaked", "timestamp"])
    for i, e in enumerate(result["events"]):
        w.writerow([i, e["op"], e["line"], e["address"], e["size"], e["caller_ip"],
                    "yes" if e["leaked"] else "no", e["timestamp_ms"]])
    w.writerow([])
    w.writerow(["per_callsite", "caller_ip", "line", "calls", "total_bytes"])
    for cs in result["per_callsite"]:
        w.writerow(["", cs["caller_ip"], cs["line"], cs["calls"], cs["total_size"]])
    w.writerow([])
    w.writerow(["leaks", "address", "size", "caller_ip", "line", "var", "op"])
    for l in result["leaks"]:
        w.writerow(["", l["address"], l["size"], l["caller_ip"], l["line"], l["var"], l["op"]])
    w.writerow([])
    w.writerow(["double_frees", "kind", "address", "var", "line", "first_free_line"])
    for df in result["double_frees"]:
        w.writerow(["", df["kind"], df["address"], df["var"], df["line"], df.get("first_free_line", "")])
    w.writerow([])
    s = result["stats"]
    w.writerow(["stats", "total_calls", s["total_calls"]])
    w.writerow(["stats", "total_bytes", s["total_bytes"]])
    w.writerow(["stats", "leaked_bytes", s["leaked_bytes"]])
    w.writerow(["stats", "leak_count", s["leak_count"]])
    w.writerow(["stats", "free_count", s["free_count"]])
    w.writerow(["stats", "double_free_count", s["double_free_count"]])
    return buf.getvalue()