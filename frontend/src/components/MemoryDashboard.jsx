import React from "react";

export default function MemoryDashboard({ result, onJumpToLine }) {
  if (!result) {
    return (
      <div className="empty" data-testid="dashboard-empty">
        Run the program to see allocation timeline, per-call-site breakdown, and leak summary.
      </div>
    );
  }
  const s = result.stats;
  const events = result.events || [];
  const leakAddresses = new Set((result.leaks || []).map((l) => l.address));

  return (
    <div data-testid="memory-dashboard">
      <div className="dash">
        <div className="card">
          <div className="label">Total alloc calls</div>
          <div className="value" data-testid="stat-total-calls">{s.total_calls}</div>
        </div>
        <div className="card">
          <div className="label">Total bytes</div>
          <div className="value" data-testid="stat-total-bytes">{s.total_bytes.toLocaleString()}</div>
        </div>
        <div className={`card ${s.leak_count > 0 ? "alert" : "ok"}`}>
          <div className="label">Leaks</div>
          <div className="value" data-testid="stat-leaks">{s.leak_count}</div>
        </div>
        <div className={`card ${s.leaked_bytes > 0 ? "alert" : "ok"}`}>
          <div className="label">Leaked bytes</div>
          <div className="value" data-testid="stat-leaked-bytes">{s.leaked_bytes.toLocaleString()}</div>
        </div>
      </div>

      <div className="timeline" data-testid="timeline">
        <h4>Allocation Timeline</h4>
        <div className="events">
          {events.map((e, i) => {
            const isAlloc = !e.op.startsWith("free");
            const isLeak = isAlloc && leakAddresses.has(e.address);
            const isUnknown = e.op === "free(unknown)";
            const cls = isAlloc
              ? `ev alloc${isLeak ? " leak" : ""}`
              : isUnknown
              ? "ev free unknown"
              : "ev free";
            const title = `${e.op} | ${e.size} B | ${e.address} `;
            return (
              <span
                key={i}
                className={cls}
                title={title}
                data-testid={`timeline-event-${i}`}

                style={{ cursor: "pointer" }}
              />
            );
          })}
        </div>
        <div style={{ display: "flex", gap: 14, marginTop: 8, fontSize: 11, color: "var(--vsc-fg-muted)" }}>
          <span><span className="ev alloc" style={{ display: "inline-block", verticalAlign: "middle" }} /> alloc</span>
          <span><span className="ev alloc leak" style={{ display: "inline-block", verticalAlign: "middle" }} /> leaked alloc</span>
          <span><span className="ev free" style={{ display: "inline-block", verticalAlign: "middle" }} /> free</span>
          <span><span className="ev free unknown" style={{ display: "inline-block", verticalAlign: "middle" }} /> free unknown</span>
        </div>
      </div>

      {/* <div className="callsites" data-testid="callsites">
        <h4>Allocations per Call Site</h4>
        <table>
          <thead>
            <tr><th>Caller IP</th><th>Line</th><th>Calls</th><th>Bytes</th></tr>
          </thead>
          <tbody>
            {(result.per_callsite || []).map((cs, i) => (
              <tr key={i} onClick={() => onJumpToLine && onJumpToLine(cs.line)} style={{ cursor: "pointer" }} data-testid={`callsite-row-${i}`}>
                <td>{cs.caller_ip}</td>
                <td>{cs.line || "-"}</td>
                <td>{cs.calls}</td>
                <td>{cs.total_size.toLocaleString()}</td>
              </tr>
            ))}
            {(result.per_callsite || []).length === 0 && (
              <tr><td colSpan={4} style={{ color: "var(--vsc-fg-muted)" }}>No call sites recorded</td></tr>
            )}
          </tbody>
        </table>
      </div> */}
    </div>
  );
}