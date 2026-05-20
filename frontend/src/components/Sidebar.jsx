import React from "react";
import { FileCode2, FileText, ChevronRight, ChevronDown } from "lucide-react";

export default function Sidebar({ files, activeFile, onOpen }) {
  const fileNames = Object.keys(files);
  const [open, setOpen] = React.useState(true);

  return (
    <aside className="pintrace-sidebar" data-testid="sidebar">
      <div className="header">
        <span>Explorer</span>
        <span style={{ fontSize: 10 }}>•••</span>
      </div>
      <div className="file-list">
        <div
          className="file-item"
          style={{ fontWeight: 600, fontSize: 11, textTransform: "uppercase", color: "var(--vsc-fg-muted)", letterSpacing: 0.6 }}
          onClick={() => setOpen(!open)}
          data-testid="sidebar-folder-toggle"
        >
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          <span>pintrace-workspace</span>
        </div>
        {open && fileNames.map((name) => (
          <div
            key={name}
            className={`file-item ${name === activeFile ? "active" : ""}`}
            onClick={() => onOpen(name)}
            data-testid={`sidebar-file-${name}`}
            style={{ paddingLeft: 28 }}
          >
            {name.endsWith(".c") || name.endsWith(".cpp") ? (
              <FileCode2 size={14} className="icon" />
            ) : (
              <FileText size={14} className="icon" />
            )}
            <span>{name}</span>
          </div>
        ))}
      </div>
    </aside>
  );
}