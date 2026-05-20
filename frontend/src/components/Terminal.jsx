import React from "react";

export default function Terminal({ result, running }) {
  if (running) {
    return (
      <div className="empty" data-testid="terminal-running">
        <span>► Running pin -t memtrace.so -- ./your_program ...</span>
      </div>
    );
  }
  if (!result) {
    return (
      <div className="empty" data-testid="terminal-empty">
        <span>Press Run to instrument the program with the Pin memtrace tool.</span>
        <span style={{ opacity: 0.7 }}>Output appears here.</span>
      </div>
    );
  }
  const lines = (result.memtrace_out || "").split("\n");
  return (
    <pre data-testid="terminal-output">
{lines.map((l, i) => {
  const isLeak = l.startsWith("LEAK:");
  const isFree = l.startsWith("Free:");
  const isAlloc = l.startsWith("Memory Allocation");
  const isHeader = l.match(/^[A-Z][A-Z ]+/) && l.includes(" ");
  const color = isLeak
    ? "#f14c4c"
    : isAlloc
    ? "#4ec9b0"
    : isFree
    ? "#9cdcfe"
    : isHeader
    ? "#cca700"
    : "var(--vsc-fg)";
  return (
    <span key={i} style={{ color, display: "block" }}>
      {l || "\u00a0"}
    </span>
  );
})}
    </pre>
  );
}
