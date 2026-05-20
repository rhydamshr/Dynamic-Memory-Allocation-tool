#include "pin.H"
#include <iostream>
#include <fstream>
#include <map>

using std::endl;
using std::ofstream;
using std::string;


// Data Structures


struct AllocInfo
{
    size_t size;
    string allocator;
};

std::map<ADDRINT, AllocInfo> activeAllocations;
std::map<ADDRINT, bool> freedPointers;
std::map<ADDRINT, bool> seenFreed;  

size_t totalAllocated = 0;
size_t totalAllocCalls = 0;

ofstream out;


// Original function pointers


AFUNPTR mallocOrig = 0;
AFUNPTR callocOrig = 0;
AFUNPTR reallocOrig = 0;
AFUNPTR freeOrig = 0;
VOID BeforeFreeCheck(ADDRINT ptr)
{
    if (ptr == 0)
        return;

    if (seenFreed.count(ptr))
    {
        out << "DOUBLEFREE "
            << (void*)ptr
            << endl;
    }
    else
    {
        seenFreed[ptr] = true;
    }
}


// malloc wrapper


VOID* MallocWrapper(CONTEXT* ctxt, AFUNPTR origFunc, size_t size)
{
    VOID* ret;

    PIN_CallApplicationFunction(
        ctxt,
        PIN_ThreadId(),
        CALLINGSTD_DEFAULT,
        origFunc,
        NULL,
        PIN_PARG(void*), &ret,
        PIN_PARG(size_t), size,
        PIN_PARG_END()
    );

    if (ret)
    {
        activeAllocations[(ADDRINT)ret] = {
            size,
            "malloc"
        };

        totalAllocated += size;
        totalAllocCalls++;

        out << "MALLOC "
            << ret
            << " size="
            << size
            << endl;
    }

    return ret;
}
INT32 line = 0;
string file;

PIN_GetSourceLocation(
    ip,
    NULL,
    &line,
    &file
);


// calloc wrapper


VOID* CallocWrapper(
    CONTEXT* ctxt,
    AFUNPTR origFunc,
    size_t count,
    size_t size,
    ADDRINT ip
)
{
    VOID* ret;

    PIN_CallApplicationFunction(
        ctxt,
        PIN_ThreadId(),
        CALLINGSTD_DEFAULT,
        origFunc,
        NULL,
        PIN_PARG(void*), &ret,
        PIN_PARG(size_t), count,
        PIN_PARG(size_t), size,
        PIN_PARG_END()
    );

    size_t total = count * size;

    if (ret)
    {
        activeAllocations[(ADDRINT)ret] = {
            total,
            "calloc"
        };

        totalAllocated += total;
        totalAllocCalls++;

        out << "CALLOC "
            << ret
            << " size="
            << total
            << endl;
    }

    return ret;
}


// realloc wrapper


VOID* ReallocWrapper(
    CONTEXT* ctxt,
    AFUNPTR origFunc,
    VOID* oldPtr,
    size_t newSize,
    ADDRINT ip
)
{
    VOID* ret;

    PIN_CallApplicationFunction(
        ctxt,
        PIN_ThreadId(),
        CALLINGSTD_DEFAULT,
        origFunc,
        NULL,
        PIN_PARG(void*), &ret,
        PIN_PARG(void*), oldPtr,
        PIN_PARG(size_t), newSize,
        PIN_PARG_END()
    );

    // remove old allocation
    if (oldPtr)
    {
        activeAllocations.erase((ADDRINT)oldPtr);
    }

    // add new allocation
    if (ret)
    {
        activeAllocations[(ADDRINT)ret] = {
            newSize,
            "realloc"
        };

        totalAllocated += newSize;
        totalAllocCalls++;

        out << "REALLOC "
            << ret
            << " size="
            << newSize
            << endl;
    }

    return ret;
}


// free wrapper

VOID FreeWrapper(
    CONTEXT* ctxt,
    AFUNPTR origFunc,
    VOID* ptr,
    ADDRINT ip
)
{
    out << "FREE "
        << ptr
        << endl;

    // NULL free -> treat as probable double free


    if (!ptr)
    {
        out << "DOUBLEFREE NULL"
            << endl;

        return;
    }

    ADDRINT addr = (ADDRINT)ptr;


    // DOUBLE FREE DETECTED


    if (freedPointers.count(addr))
    {
        out << "DOUBLEFREE "
            << ptr
            << endl;

        // IMPORTANT:
        // do NOT call real free again
        return;
    }


    // NORMAL FREE


    if (activeAllocations.count(addr))
    {
        activeAllocations.erase(addr);

        freedPointers[addr] = true;
    }
    else
    {
        out << "FREEUNKNOWN "
            << ptr
            << endl;
    }


    // REAL FREE


    PIN_CallApplicationFunction(
        ctxt,
        PIN_ThreadId(),
        CALLINGSTD_DEFAULT,
        origFunc,
        NULL,
        PIN_PARG(void),
        PIN_PARG(void*), ptr,
        PIN_PARG_END()
    );
}

// Image instrumentation


VOID ImageLoad(IMG img, VOID* v)
{
    RTN mallocRtn = RTN_FindByName(img, "malloc");

    if (RTN_Valid(mallocRtn))
    {
        mallocOrig = RTN_ReplaceSignature(
            mallocRtn,
            AFUNPTR(MallocWrapper),
            IARG_CONTEXT,
            IARG_ORIG_FUNCPTR,
            IARG_FUNCARG_ENTRYPOINT_VALUE, 0,
            IARG_RETURN_IP,
            IARG_END
        );
    }

    RTN callocRtn = RTN_FindByName(img, "__libc_calloc");

    if (!RTN_Valid(callocRtn))
    {
        callocRtn = RTN_FindByName(img, "calloc");
    }

    if (RTN_Valid(callocRtn))
    {
        callocOrig = RTN_ReplaceSignature(
            callocRtn,
            AFUNPTR(CallocWrapper),
            IARG_CONTEXT,
            IARG_ORIG_FUNCPTR,
            IARG_FUNCARG_ENTRYPOINT_VALUE, 0,
            IARG_FUNCARG_ENTRYPOINT_VALUE, 1,
            IARG_RETURN_IP,
            IARG_END
        );
    }

    RTN reallocRtn = RTN_FindByName(img, "__libc_realloc");

    if (!RTN_Valid(reallocRtn))
    {
        reallocRtn = RTN_FindByName(img, "realloc");
    }

    if (RTN_Valid(reallocRtn))
    {
        reallocOrig = RTN_ReplaceSignature(
            reallocRtn,
            AFUNPTR(ReallocWrapper),
            IARG_CONTEXT,
            IARG_ORIG_FUNCPTR,
            IARG_FUNCARG_ENTRYPOINT_VALUE, 0,
            IARG_FUNCARG_ENTRYPOINT_VALUE, 1,
            IARG_RETURN_IP,
            IARG_END
        );
    }

    RTN freeRtn = RTN_FindByName(img, "free");

    if (RTN_Valid(freeRtn))
    {
        RTN_Open(freeRtn);

        RTN_InsertCall(
            freeRtn,
            IPOINT_BEFORE,
            (AFUNPTR)BeforeFreeCheck,
            IARG_FUNCARG_ENTRYPOINT_VALUE, 0,
            
            IARG_END
        );

        RTN_Close(freeRtn);
        freeOrig = RTN_ReplaceSignature(
            freeRtn,
            AFUNPTR(FreeWrapper),
            IARG_CONTEXT,
            IARG_ORIG_FUNCPTR,
            IARG_FUNCARG_ENTRYPOINT_VALUE, 0,
            IARG_RETURN_IP,
            IARG_END
        );
    }
}


// Final report


VOID Fini(INT32 code, VOID* v)
{
    out << endl;
    out << "========== MEMORY REPORT ==========" << endl;

    out << "Total Allocation Calls: "
        << totalAllocCalls
        << endl;

    out << "Total Bytes Allocated: "
        << totalAllocated
        << endl;

    size_t totalLeaked = 0;

    out << endl;
    out << "========== LEAKS ==========" << endl;

    if (activeAllocations.empty())
    {
        out << "No leaks detected"
            << endl;
    }
    else
    {
        for (auto const& [ptr, info] : activeAllocations)
        {
            out << "LEAK "
                << (void*)ptr
                << " size="
                << info.size
                << " allocator="
                << info.allocator
                << endl;

            totalLeaked += info.size;
        }
    }

    out << endl;
    out << "TOTAL LEAKED: "
        << totalLeaked
        << " bytes"
        << endl;

    out.close();
}


// Main


int main(int argc, char *argv[])
{
    PIN_InitSymbols();

    if (PIN_Init(argc, argv))
    {
        return 1;
    }

    out.open("memtrace.out");

    IMG_AddInstrumentFunction(ImageLoad, 0);

    PIN_AddFiniFunction(Fini, 0);

    PIN_StartProgram();

    return 0;
}