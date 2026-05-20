import React from "react";
import { Download } from "lucide-react";

function parseCsv(text) {
  // very basic CSV parser sufficient for our generated content
  return text
    .split(/\r?\n/)
    .filter((l) => l.length > 0)
    .map((line) => {
      const out = [];
      let cur = "";
      let inQ = false;
      for (let i = 0; i < line.length; i++) {
        const c = line[i];
        if (c === '"') inQ = !inQ;
        else if (c === "," && !inQ) {
          out.push(cur);
          cur = "";
        } else cur += c;
      }
      out.push(cur);
      return out;
    });
}

export default function CSVReport({ result }) {
  if (!result) {
    return (
      <div className="empty" data-testid="csv-empty">
        Run the program to generate a CSV memory report.
      </div>
    );
  }
  const rows = parseCsv(result.csv_report || "");
  const leaked = new Set((result.leaks || []).map((l) => l.address));

  function download() {
    const blob = new Blob([result.csv_report], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `memtrace_${result.id}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div data-testid="csv-report">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <div style={{ fontSize: 11, color: "var(--vsc-fg-muted)", textTransform: "uppercase", letterSpacing: 0.6 }}>
          memtrace_{result.id?.slice(0, 8)}.csv  ({rows.length} rows)
        </div>
        <button className="btn btn-ghost" onClick={download} data-testid="csv-download-btn">
          <Download size={12} /> Download CSV
        </button>
      </div>
      <table className="csv-table">
        <tbody>
          {rows.map((r, i) => {
            // header heuristic: row that starts with "index" or "per_callsite" or "leaks"
            const isHeader = ["index", "per_callsite", "leaks", "stats", "#"].includes(r[0]);
            const isLeakRow = r.length >= 7 && leaked.has(r[3]) && /^\d+$/.test(r[0]);
            if (isHeader && (r[0] === "per_callsite" || r[0] === "leaks" || r[0] === "stats")) {
              return (
                <tr key={i}>
                  <td className="section" colSpan={r.length}>{r.join(" › ")}</td>
                </tr>
              );
            }
            return (
              <tr key={i} className={isLeakRow ? "leak" : ""}>
                {r.map((c, j) =>
                  isHeader ? <th key={j}>{c}</th> : <td key={j}>{c}</td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
