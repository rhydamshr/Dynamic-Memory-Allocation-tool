# PinTrace IDE

PinTrace IDE is a browser-based memory debugging environment powered by Intel Pin.

It allows users to:
- write and run C programs,
- instrument them dynamically using a custom Intel Pin Pintool,
- detect memory leaks,
- detect probable double frees,
- visualize allocations and frees,
- inspect memory statistics and CSV reports.

---

# Features

## Supported Memory Operations

- malloc
- calloc
- realloc
- free

## Leak Detection

Detects memory that was allocated but never freed.

Shows:
- leaked address
- leaked size
- allocator type
- total leaked bytes

## Double-Free Detection

Detects probable double frees and reports them as warnings.

## Dashboard

Displays:
- total allocations
- total allocated bytes
- leak count
- total leaked bytes

## CSV Reports

Exports structured memory instrumentation data.

## Problems Panel

Highlights:
- memory leaks
- probable double frees

---

# Project Structure

```text
frontend/     -> React frontend
backend/      -> FastAPI backend
memtrace/     -> Intel Pin Pintool
```

---

# Requirements

This project is intended to run on Linux / WSL.

---

# Steps to run:

Ubuntu on WSL2

Install required packages:

sudo apt update

sudo apt install -y \
    build-essential \
    python3 \
    python3-pip \
    python3-venv \
    git

Install Node.js 18+ separately.

Intel Pin Setup
1. Download Intel Pin

Download Intel Pin for Linux from:

https://www.intel.com/content/www/us/en/developer/articles/tool/pin-a-binary-instrumentation-tool-downloads.html

Extract it somewhere convenient.

Example:

/home/your_user/pin
2. Copy MemTrace Tool

Copy the memtrace folder into:

PIN_ROOT/source/tools/

Example:

cp -r memtrace ~/pin/source/tools/MemTrace
3. Build the Pintool
cd ~/pin/source/tools/MemTrace

make clean
make TARGET=intel64

After successful build, this file should exist:

obj-intel64/memtrace.so
Backend Setup
1. Create Backend Environment File

Create:

backend/.env

Paste:

MONGO_URL="mongodb://localhost:27017"
DB_NAME="test_database"
CORS_ORIGINS="*"

PIN_ROOT=/home/your_user/pin

PIN_TOOL_LIB=/home/your_user/pin/source/tools/MemTrace/obj-intel64/memtrace.so

CC=g++

IMPORTANT:
Replace /home/your_user/pin with your actual Pin path.

2. Create Python Virtual Environment
cd backend

python3 -m venv venv_linux

Activate it:

source venv_linux/bin/activate
3. Install Backend Dependencies
pip install -r requirements.txt
4. Run Backend
uvicorn server:app --host 0.0.0.0 --port 8001 --reload

Backend runs at:

http://localhost:8001
Frontend Setup
1. Create Frontend Environment File

Create:

frontend/.env

Paste:

REACT_APP_BACKEND_URL=http://localhost:8001
WDS_SOCKET_PORT=443
ENABLE_HEALTH_CHECK=false
2. Install Frontend Dependencies
cd frontend

npm install
3. Run Frontend
npm start

Frontend runs at:

http://localhost:3000
Usage
Open the frontend in browser.
Write or paste a C program.
Press Run.
The backend:
compiles the program,
launches Intel Pin,
instruments memory operations,
parses results,
sends structured data to frontend.
View:
terminal output
memory dashboard
CSV report
problems/warnings panel
Example Memory Leak
char *p = malloc(64);
// never freed
Example Double Free
free(p);
free(p);
Technologies Used
Frontend
React
Monaco Editor
Backend
FastAPI
Python
Instrumentation
Intel Pin
Custom C++ Pintool
Notes
Intended for Linux / WSL environments.
Runtime/internal libc allocations may appear in reports.
Double-free detection is heuristic-based.