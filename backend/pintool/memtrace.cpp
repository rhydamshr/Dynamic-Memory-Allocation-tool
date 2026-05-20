"/*
 * memtrace.cpp  --  Intel Pin tool: full malloc-family instrumentation.
 *
 *  Tracks: malloc, calloc, realloc, free, aligned_alloc, posix_memalign,
 *          _aligned_malloc / _aligned_free (Windows MSVCRT).
 *
 *  Output: memtrace.out
 *
 *  Build (Linux):
 *      $ cp memtrace.cpp $PIN_ROOT/source/tools/MyPinTool/
 *      $ cd $PIN_ROOT/source/tools/MyPinTool/
 *      $ make obj-intel64/memtrace.so TARGET=intel64
 *
 *  Build (Windows, after installing Pin for Windows + MSVC build tools):
 *      > nmake TARGET=intel64
 *
 *  Run:
 *      $ pin -t obj-intel64/memtrace.so -- ./your_program
 */

#include "pin.H"
#include <iostream>
#include <fstream>
#include <map>
#include <string>

using std::ofstream;
using std::endl;
using std::string;

struct AllocInfo {
    size_t  size;
    ADDRINT callerIp;
    string  allocator; // "malloc", "calloc", "realloc", "aligned_alloc", "posix_memalign"
};

// -- Globals --------------------------------------------------------------
std::map<ADDRINT, AllocInfo>      activeAllocations;
std::map<ADDRINT, size_t>         perCallSiteBytes;
std::map<ADDRINT, size_t>         perCallSiteCount;

// Per-thread pending state for return-value pairing
std::map<THREADID, size_t>        pendingSize;
std::map<THREADID, ADDRINT>       pendingReallocPtr;
std::map<THREADID, ADDRINT>       pendingPosixMemalignArg; // void** (output)
std::map<THREADID, size_t>        pendingPosixMemalignSize;
std::map<THREADID, string>        pendingAllocator;

size_t totalAllocatedBytes = 0;
size_t totalMallocCalls    = 0;

ofstream out;

// -- Helpers --------------------------------------------------------------
static VOID RecordAlloc(ADDRINT ret, size_t sz, ADDRINT ip, const string &name) {
    if (ret == 0) return;
    AllocInfo info;
    info.size      = sz;
    info.callerIp  = ip;
    info.allocator = name;
    activeAllocations[ret]  = info;
    totalAllocatedBytes    += sz;
    totalMallocCalls       += 1;
    perCallSiteBytes[ip]   += sz;
    perCallSiteCount[ip]   += 1;
    out << "Memory Allocation address: " << (void *) ret
        << " of size =" << sz << " bytes
"
        << "Called by Instruction pointer address: " << (void *) ip << "
"
        << "Allocator: " << name << "
" << endl;
}

static VOID RecordFree(ADDRINT ptr, const string &reason) {
    if (ptr == 0) return;
    if (activeAllocations.count(ptr)) {
        out << "Free:  " << (void *) ptr
            << " (" << reason << ", origin=" << activeAllocations[ptr].allocator << ")"
            << endl;
        activeAllocations.erase(ptr);
    } else {
        out << "Free:  " << (void *) ptr << " (Unknown source)" << endl;
    }
}

// -- malloc(size) ---------------------------------------------------------
VOID BeforeMalloc(size_t size, THREADID tid) {
    pendingSize[tid]      = size;
    pendingAllocator[tid] = "malloc";
}

VOID AfterAlloc(ADDRINT ret, ADDRINT ip, THREADID tid) {
    size_t sz = pendingSize[tid];
    string name = pendingAllocator[tid];
    if (name.empty()) name = "alloc";
    RecordAlloc(ret, sz, ip, name);
}

// -- calloc(nmemb, size) --------------------------------------------------
VOID BeforeCalloc(size_t n, size_t sz, THREADID tid) {
    pendingSize[tid]      = n * sz;
    pendingAllocator[tid] = "calloc";
}

// -- realloc(ptr, size) ---------------------------------------------------
VOID BeforeRealloc(ADDRINT oldPtr, size_t newSize, THREADID tid) {
    pendingReallocPtr[tid] = oldPtr;
    pendingSize[tid]       = newSize;
    pendingAllocator[tid]  = "realloc";
}

VOID AfterRealloc(ADDRINT ret, ADDRINT ip, THREADID tid) {
    ADDRINT oldPtr = pendingReallocPtr[tid];
    size_t  sz     = pendingSize[tid];
    if (oldPtr != 0) {
        // implicit free of old region (only if realloc moved or shrank)
        RecordFree(oldPtr, "realloc-implicit-free");
    }
    RecordAlloc(ret, sz, ip, "realloc");
}

// -- aligned_alloc(alignment, size) ---------------------------------------
VOID BeforeAlignedAlloc(size_t alignment, size_t size, THREADID tid) {
    pendingSize[tid]      = size;
    pendingAllocator[tid] = "aligned_alloc";
}

// -- _aligned_malloc(size, alignment)  (Windows) --------------------------
VOID BeforeWinAlignedMalloc(size_t size, size_t alignment, THREADID tid) {
    pendingSize[tid]      = size;
    pendingAllocator[tid] = "_aligned_malloc";
}

// -- posix_memalign(void **out, size_t alignment, size_t size) ------------
VOID BeforePosixMemalign(ADDRINT outPtr, size_t alignment, size_t size, THREADID tid) {
    pendingPosixMemalignArg[tid]  = outPtr;
    pendingPosixMemalignSize[tid] = size;
    pendingAllocator[tid]         = "posix_memalign";
}

VOID AfterPosixMemalign(ADDRINT ret, ADDRINT ip, THREADID tid) {
    if (ret != 0) return; // posix_memalign returns 0 on success
    ADDRINT outArg = pendingPosixMemalignArg[tid];
    size_t  sz     = pendingPosixMemalignSize[tid];
    if (outArg == 0) return;
    ADDRINT allocatedPtr = 0;
    PIN_SafeCopy(&allocatedPtr, (const VOID *) outArg, sizeof(ADDRINT));
    RecordAlloc(allocatedPtr, sz, ip, "posix_memalign");
}

// -- free(ptr) / _aligned_free(ptr) ---------------------------------------
VOID BeforeFree(ADDRINT ptr) { RecordFree(ptr, "free"); }
VOID BeforeAlignedFree(ADDRINT ptr) { RecordFree(ptr, "_aligned_free"); }

// -- Routine-level instrumentation ----------------------------------------
static bool NameIs(const string &n, const char *t) {
    return n == t || n == (string("__libc_") + t);
}

VOID Routine(RTN rtn, VOID *v) {
    string name = RTN_Name(rtn);

    if (NameIs(name, "malloc")) {
        RTN_Open(rtn);
        RTN_InsertCall(rtn, IPOINT_BEFORE, (AFUNPTR) BeforeMalloc,
                       IARG_FUNCARG_ENTRYPOINT_VALUE, 0,
                       IARG_THREAD_ID, IARG_END);
        RTN_InsertCall(rtn, IPOINT_AFTER, (AFUNPTR) AfterAlloc,
                       IARG_FUNCRET_EXITPOINT_VALUE,
                       IARG_RETURN_IP, IARG_THREAD_ID, IARG_END);
        RTN_Close(rtn);
    } else if (NameIs(name, "calloc")) {
        RTN_Open(rtn);
        RTN_InsertCall(rtn, IPOINT_BEFORE, (AFUNPTR) BeforeCalloc,
                       IARG_FUNCARG_ENTRYPOINT_VALUE, 0,
                       IARG_FUNCARG_ENTRYPOINT_VALUE, 1,
                       IARG_THREAD_ID, IARG_END);
        RTN_InsertCall(rtn, IPOINT_AFTER, (AFUNPTR) AfterAlloc,
                       IARG_FUNCRET_EXITPOINT_VALUE,
                       IARG_RETURN_IP, IARG_THREAD_ID, IARG_END);
        RTN_Close(rtn);
    } else if (NameIs(name, "realloc")) {
        RTN_Open(rtn);
        RTN_InsertCall(rtn, IPOINT_BEFORE, (AFUNPTR) BeforeRealloc,
                       IARG_FUNCARG_ENTRYPOINT_VALUE, 0,
                       IARG_FUNCARG_ENTRYPOINT_VALUE, 1,
                       IARG_THREAD_ID, IARG_END);
        RTN_InsertCall(rtn, IPOINT_AFTER, (AFUNPTR) AfterRealloc,
                       IARG_FUNCRET_EXITPOINT_VALUE,
                       IARG_RETURN_IP, IARG_THREAD_ID, IARG_END);
        RTN_Close(rtn);
    } else if (name == "aligned_alloc") {
        RTN_Open(rtn);
        RTN_InsertCall(rtn, IPOINT_BEFORE, (AFUNPTR) BeforeAlignedAlloc,
                       IARG_FUNCARG_ENTRYPOINT_VALUE, 0,
                       IARG_FUNCARG_ENTRYPOINT_VALUE, 1,
                       IARG_THREAD_ID, IARG_END);
        RTN_InsertCall(rtn, IPOINT_AFTER, (AFUNPTR) AfterAlloc,
                       IARG_FUNCRET_EXITPOINT_VALUE,
                       IARG_RETURN_IP, IARG_THREAD_ID, IARG_END);
        RTN_Close(rtn);
    } else if (name == "_aligned_malloc") {
        RTN_Open(rtn);
        RTN_InsertCall(rtn, IPOINT_BEFORE, (AFUNPTR) BeforeWinAlignedMalloc,
                       IARG_FUNCARG_ENTRYPOINT_VALUE, 0,
                       IARG_FUNCARG_ENTRYPOINT_VALUE, 1,
                       IARG_THREAD_ID, IARG_END);
        RTN_InsertCall(rtn, IPOINT_AFTER, (AFUNPTR) AfterAlloc,
                       IARG_FUNCRET_EXITPOINT_VALUE,
                       IARG_RETURN_IP, IARG_THREAD_ID, IARG_END);
        RTN_Close(rtn);
    } else if (name == "posix_memalign") {
        RTN_Open(rtn);
        RTN_InsertCall(rtn, IPOINT_BEFORE, (AFUNPTR) BeforePosixMemalign,
                       IARG_FUNCARG_ENTRYPOINT_VALUE, 0,
                       IARG_FUNCARG_ENTRYPOINT_VALUE, 1,
                       IARG_FUNCARG_ENTRYPOINT_VALUE, 2,
                       IARG_THREAD_ID, IARG_END);
        RTN_InsertCall(rtn, IPOINT_AFTER, (AFUNPTR) AfterPosixMemalign,
                       IARG_FUNCRET_EXITPOINT_VALUE,
                       IARG_RETURN_IP, IARG_THREAD_ID, IARG_END);
        RTN_Close(rtn);
    } else if (name == "free" || name == "__libc_free" || name == "cfree") {
        RTN_Open(rtn);
        RTN_InsertCall(rtn, IPOINT_BEFORE, (AFUNPTR) BeforeFree,
                       IARG_FUNCARG_ENTRYPOINT_VALUE, 0, IARG_END);
        RTN_Close(rtn);
    } else if (name == "_aligned_free") {
        RTN_Open(rtn);
        RTN_InsertCall(rtn, IPOINT_BEFORE, (AFUNPTR) BeforeAlignedFree,
                       IARG_FUNCARG_ENTRYPOINT_VALUE, 0, IARG_END);
        RTN_Close(rtn);
    }
}

// -- Final report ---------------------------------------------------------
VOID Fini(INT32 code, VOID *v) {
    out << "
MEMORY INSTRUMENTATION REPORT
";
    out << "Total Malloc Calls:     " << totalMallocCalls   << endl;
    out << "Total Bytes Allocated:  " << totalAllocatedBytes << endl;

    out << "
Allocations per Call Site
";
    for (auto const &p : perCallSiteBytes) {
        out << "Caller: " << (void *) p.first
            << " Total: " << p.second << " bytes"
            << " (calls=" << perCallSiteCount[p.first] << ")"
            << endl;
    }

    out << "
Memory Leaks Detected
";
    size_t totalLeaked = 0;
    if (activeAllocations.empty()) {
        out << "No leaks detected" << endl;
    } else {
        for (auto const &p : activeAllocations) {
            out << "LEAK: Address " << (void *) p.first
                << " | Size: "      << p.second.size
                << " | Allocated by: " << (void *) p.second.callerIp
                << " | Allocator: " << p.second.allocator << endl;
            totalLeaked += p.second.size;
        }
    }
    out << "
Total bytes leaked: " << totalLeaked << endl;
    out.close();
}

int main(int argc, char *argv[]) {
    PIN_InitSymbols();
    if (PIN_Init(argc, argv)) return 1;
    out.open("memtrace.out");
    RTN_AddInstrumentFunction(Routine, 0);
    PIN_AddFiniFunction(Fini, 0);
    PIN_StartProgram();
    return 0;
}
"