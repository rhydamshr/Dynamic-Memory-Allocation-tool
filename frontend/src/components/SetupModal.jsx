import React, { useEffect, useState } from "react";
import { X, Download } from "lucide-react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function SetupModal({ open, onClose }) {
  const [tab, setTab] = useState("readme");
  const [readme, setReadme] = useState("Loading...");
  const [pinSrc, setPinSrc] = useState("Loading...");
  const [makefile, setMakefile] = useState("Loading...");

  useEffect(() => {
    if (!open) return;
    Promise.all([
      axios.get(`${API}/pintool/readme`).then((r) => r.data),
      axios.get(`${API}/pintool/source`).then((r) => r.data),
      axios.get(`${API}/pintool/makefile`).then((r) => r.data),
    ])
      .then(([r, s, m]) => {
        setReadme(r);
        setPinSrc(s);
        setMakefile(m);
      })
      .catch(() => {
        setReadme("Failed to load");
        setPinSrc("Failed to load");
        setMakefile("Failed to load");
      });
  }, [open]);

  if (!open) return null;

  function downloadFile(filename, content) {
    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  const current =
    tab === "readme" ? readme : tab === "source" ? pinSrc : makefile;
  const filename =
    tab === "readme" ? "README_WINDOWS.md" : tab === "source" ? "memtrace.cpp" : "makefile.rules";

  return (
    <div className="modal-overlay" data-testid="setup-modal" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header>
          <span>Pin tool — Windows setup &amp; downloads</span>
          <X size={16} style={{ cursor: "pointer" }} onClick={onClose} data-testid="setup-modal-close" />
        </header>
        <div style={{ padding: "10px 16px 0" }}>
          <div className="tabs">
            <div className={`tab ${tab === "readme" ? "active" : ""}`} onClick={() => setTab("readme")} data-testid="setup-tab-readme">
              README_WINDOWS.md
            </div>
            <div className={`tab ${tab === "source" ? "active" : ""}`} onClick={() => setTab("source")} data-testid="setup-tab-source">
              memtrace.cpp
            </div>
            <div className={`tab ${tab === "makefile" ? "active" : ""}`} onClick={() => setTab("makefile")} data-testid="setup-tab-makefile">
              makefile.rules
            </div>
            <div style={{ flex: 1 }} />
            <button className="btn btn-ghost" onClick={() => downloadFile(filename, current)} data-testid="setup-download-btn">
              <Download size={12} /> Download
            </button>
          </div>
        </div>
        <div className="body">
          <pre>{current}</pre>
        </div>
      </div>
    </div>
  );
}
