import React from "react";
import { X, FileCode2, FileText } from "lucide-react";

export default function TabBar({ openFiles, activeFile, onSelect, onClose }) {
  return (
    <div className="pintrace-tabs" data-testid="tab-bar">
      {openFiles.map((name) => (
        <div
          key={name}
          className={`tab ${name === activeFile ? "active" : ""}`}
          onClick={() => onSelect(name)}
          data-testid={`tab-${name}`}
        >
          {name.endsWith(".c") ? <FileCode2 size={12} className="icon" style={{color: "var(--vsc-accent-2)"}} /> : <FileText size={12} />}
          <span>{name}</span>
          {openFiles.length > 1 && (
            <X
              size={12}
              className="close"
              onClick={(e) => {
                e.stopPropagation();
                onClose(name);
              }}
              data-testid={`tab-close-${name}`}
            />
          )}
        </div>
      ))}
    </div>
  );
}