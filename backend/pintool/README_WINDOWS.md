"# PinTrace — Windows Demo Instructions

This document explains how to demonstrate the project end-to-end on a
Windows 10 / 11 machine using **Intel Pin for Windows**.

## 1. Prerequisites

| Tool | Version | Where |
|------|---------|-------|
| Intel Pin (Windows) | 3.28+ | https://www.intel.com/content/www/us/en/developer/articles/tool/pin-a-binary-instrumentation-tool-downloads.html |
| Visual Studio Build Tools | 2019/2022 | `Desktop development with C++` workload (MSVC + Windows SDK) |
| Python | 3.10+ | https://python.org |
| Node.js | 18+ | https://nodejs.org |
| Yarn | 1.22+ | `npm install -g yarn` |
| MongoDB Community | 6.x | https://www.mongodb.com/try/download/community |

> Pin only works on x86/x64 with binaries that match its architecture.
> Use the **x64 Native Tools Command Prompt** when building.

## 2. Build the Pin tool

```bat
:: 1) extract pin to e.g. C:\pin
:: 2) copy our tool into a new folder under source	ools
mkdir %PIN_ROOT%\source	ools\MemTrace
copy memtrace.cpp     %PIN_ROOT%\source\tools\MemTrace\
copy makefile.rules   %PIN_ROOT%\source\tools\MemTrace\

:: 3) the standard makefile lives one folder up, copy it too
copy %PIN_ROOT%\source\tools\MyPinTool\makefile %PIN_ROOT%\source\tools\MemTrace\

:: 4) open the *x64 Native Tools Command Prompt for VS 2022* and run:
cd %PIN_ROOT%\source\tools\MemTrace
nmake TARGET=intel64
```

The build produces `obj-intel64\memtrace.dll`.

Sanity check:

```bat
%PIN_ROOT%\pin.exe -t obj-intel64\memtrace.dll -- C:\Windows\System32
otepad.exe
```

(Close Notepad after a second; you should see a `memtrace.out` file
created in the working directory.)

## 3. Configure the IDE backend to use real Pin

In `backend\.env` add the following (do **not** delete existing keys):

```
PIN_ROOT=C:\pin
PIN_TOOL_LIB=C:\pin\source	ools\MemTrace\obj-intel64\memtrace.dll
CC=cl
```

## 4. Run the IDE locally

```bat
:: 1) install backend deps
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001 --reload

:: 2) in another shell, install the frontend
cd frontend
yarn install
yarn start
```

Open http://localhost:3000

## 5. Demo flow

1. The editor pre-loads `leaky.c` containing intentional leaks
   (one `malloc` is freed, two are leaked, one `realloc` is leaked,
   one `posix_memalign` is freed, one `aligned_alloc` is leaked).
2. Press **Run** (top-right). The IDE POSTs the source code to
   `POST /api/run`.
3. The backend compiles via `cl` (or `gcc`), launches `pin.exe -t memtrace.dll`,
   reads `memtrace.out`, parses it, and returns:
   - markers → red squigglies in the editor on leak lines
   - `csv_report` → CSV tab
   - `events` + `stats` → Memory Dashboard panel
   - `memtrace_out` → raw output in the Terminal panel
4. Hover over a red squiggly to see the leak size, address and allocator.

## 6. Cloud demo (no Pin installed)

If `PIN_ROOT` is **not** set, the backend automatically falls back to
the simulation engine, which performs static analysis of malloc-family
calls in the source and produces a realistic memtrace report. The IDE
labels the output as `mode: simulation`. This is what runs in the
hosted preview.

## 7. Allocator coverage

The Pin tool now hooks:

```
malloc, calloc, realloc, free, cfree,
aligned_alloc, _aligned_malloc, _aligned_free,
posix_memalign
```

`realloc` is treated as an implicit free of the old pointer followed by
an alloc of the new pointer (matching glibc semantics).
"