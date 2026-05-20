import React, { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import {
  Files, Search, GitBranch, Bug, Settings, Play, Loader2,
  Cpu, AlertTriangle, BookOpen, Terminal as TermIcon, Table, Activity, FileText
} from "lucide-react";

import Sidebar from "./Sidebar";
import TabBar from "./TabBar";
import MonacoEditor from "./MonacoEditor";
import Terminal from "./Terminal";
import MemoryDashboard from "./MemoryDashboard";
import CSVReport from "./CSVReport";
import SetupModal from "./SetupModal";
import { SAMPLE_FILES, FILE_LANG } from "../data/sampleCode";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function IDE() {
  const [files, setFiles] = useState({ ...SAMPLE_FILES });
  const [activeFile, setActiveFile] = useState("leaky.c");
  const [openFiles, setOpenFiles] = useState(["leaky.c"]);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [panelTab, setPanelTab] = useState("terminal");
  const [setupOpen, setSetupOpen] = useState(false);
  const [pinAvailable, setPinAvailable] = useState(false);
  const editorJumpRef = useRef(null);

  // Health check (shows mode badge)
  useEffect(() => {
    axios.get(`${API}/health`).then((r) => setPinAvailable(!!r.data.pin_available)).catch(() => {});
  }, []);

  // Restore from localStorage if present
  useEffect(() => {
    try {
      const cached = localStorage.getItem("pintrace.files");
      if (cached) setFiles(JSON.parse(cached));
    } catch (_) {}
  }, []);

  function persist(next) {
    setFiles(next);
    try {
      localStorage.setItem("pintrace.files", JSON.stringify(next));
    } catch (_) {}
  }

  function openFile(name) {
    if (!openFiles.includes(name)) setOpenFiles([...openFiles, name]);
    setActiveFile(name);
  }
  function closeFile(name) {
    const next = openFiles.filter((f) => f !== name);
    setOpenFiles(next);
    if (activeFile === name && next.length) setActiveFile(next[next.length - 1]);
  }

  async function runCode() {
    setRunning(true);
    setError(null);
    try {
      const code = files[activeFile] ?? "";
      const res = await axios.post(`${API}/run`, {
        code,
        filename: activeFile,
        use_real_pin: pinAvailable,
      });
      setResult(res.data);
      setPanelTab(res.data.markers?.length ? "problems" : "terminal");
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setRunning(false);
    }
  }

  // Markers go to Monaco only for the active C file
  const monacoMarkers = useMemo(() => {
    if (!result || !activeFile.endsWith(".c")) return [];
    return result.markers || [];
  }, [result, activeFile]);

  const language = FILE_LANG[activeFile] || "plaintext";

  // keyboard shortcut: Ctrl/Cmd+Enter
  useEffect(() => {
    function handler(e) {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        if (!running) runCode();
      }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [files, activeFile, running, pinAvailable]);

  function handleEditorChange(v) {
    const next = { ...files, [activeFile]: v };
    persist(next);
  }

  function jumpToLine(line) {
    if (editorJumpRef.current) editorJumpRef.current(line);
  }

  return (
    <div className="pintrace-shell" data-testid="ide-shell">
      {/* Title bar */}
      <div className="pintrace-titlebar">
        <div className="traffic">
          <span className="r" /><span className="y" /><span className="g" />
        </div>
        <div className="title">
          {activeFile} — PinTrace IDE
        </div>
        <div className="actions">
          <button
            className="btn btn-ghost"
            onClick={() => setSetupOpen(true)}
            data-testid="open-setup-btn"
            title="Pin tool source + Windows setup"
          >
            <BookOpen size={12} /> Pin Tool & Setup
          </button>
          <button
            className="btn btn-run"
            disabled={running || !activeFile.endsWith(".c")}
            onClick={runCode}
            data-testid="run-btn"
            title="Run with Pin (Ctrl/Cmd + Enter)"
          >
            {running ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} fill="#fff" />}
            {running ? "Running..." : "Run"}
          </button>
        </div>
      </div>

      {/* Menu bar */}
      <div className="pintrace-menubar" data-testid="menubar">
        <span className="menu-item">File</span>
        <span className="menu-item">Edit</span>
        <span className="menu-item">View</span>
        <span className="menu-item">Run</span>
        <span className="menu-item" onClick={() => setSetupOpen(true)}>Help</span>
        <div className="spacer" />
        <span className="badge" data-testid="mode-badge">
          {pinAvailable ? "Real Pin" : "Simulation"}
        </span>
        <span className="badge" data-testid="pin-status-badge">
          {pinAvailable ? "PIN_ROOT detected" : "no PIN_ROOT"}
        </span>
      </div>

      {/* Main area */}
      <div className="pintrace-main">
        <nav className="pintrace-activitybar" data-testid="activity-bar">
          <button className="active" title="Explorer" data-testid="activity-explorer"><Files size={22} /></button>
          <button title="Search" data-testid="activity-search"><Search size={22} /></button>
          <button title="Source Control" data-testid="activity-source"><GitBranch size={22} /></button>
          <button title="Run & Debug" data-testid="activity-debug" onClick={runCode}><Bug size={22} /></button>
          <div style={{ flex: 1 }} />
          <button title="Settings" data-testid="activity-settings" onClick={() => setSetupOpen(true)}><Settings size={22} /></button>
        </nav>

        <Sidebar files={files} activeFile={activeFile} onOpen={openFile} />

        <div className="pintrace-editor-area">
          <TabBar
            openFiles={openFiles}
            activeFile={activeFile}
            onSelect={setActiveFile}
            onClose={closeFile}
          />
          <div className="pintrace-editor-wrap">
            <EditorWithJump
              value={files[activeFile] ?? ""}
              onChange={handleEditorChange}
              language={language}
              markers={monacoMarkers}
              jumpRef={editorJumpRef}
            />

            {/* Bottom panel */}
            <div className="pintrace-panel" data-testid="bottom-panel">
              <div className="pintrace-panel-header">
                <div
                  className={`tab ${panelTab === "terminal" ? "active" : ""}`}
                  onClick={() => setPanelTab("terminal")}
                  data-testid="panel-tab-terminal"
                >
                  <TermIcon size={11} style={{ display: "inline", marginRight: 4 }} />
                  Memtrace Output
                </div>
                <div
                  className={`tab ${panelTab === "dashboard" ? "active" : ""}`}
                  onClick={() => setPanelTab("dashboard")}
                  data-testid="panel-tab-dashboard"
                >
                  <Activity size={11} style={{ display: "inline", marginRight: 4 }} />
                  Memory Dashboard
                </div>
                <div
                  className={`tab ${panelTab === "csv" ? "active" : ""}`}
                  onClick={() => setPanelTab("csv")}
                  data-testid="panel-tab-csv"
                >
                  <Table size={11} style={{ display: "inline", marginRight: 4 }} />
                  CSV Report
                </div>
                <div
                  className={`tab ${panelTab === "problems" ? "active" : ""}`}
                  onClick={() => setPanelTab("problems")}
                  data-testid="panel-tab-problems"
                >
                  <AlertTriangle size={11} style={{ display: "inline", marginRight: 4 }} />
                  Problems
                  {result?.markers?.length > 0 && <span className="count">{result.markers.length}</span>}
                </div>
                <div style={{ flex: 1 }} />
                {error && <span style={{ color: "#f14c4c", fontSize: 11, paddingRight: 8 }}>{String(error)}</span>}
              </div>
              <div className="pintrace-panel-body">
                {panelTab === "terminal" && <Terminal result={result} running={running} />}
                {panelTab === "dashboard" && <MemoryDashboard result={result} onJumpToLine={jumpToLine} />}
                {panelTab === "csv" && <CSVReport result={result} />}
                {panelTab === "problems" && <Problems result={result} onJumpToLine={jumpToLine} />}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Status bar */}
      <div className={`pintrace-statusbar ${running ? "busy" : ""}`} data-testid="status-bar">
        <span className="item"><Cpu size={11} /> {result?.mode || (pinAvailable ? "real-pin" : "simulation")}</span>
        <span className="item">{language.toUpperCase()}</span>
        <span className="item">UTF-8</span>
        {result && (
          <>
            <span className="item">{result.stats.total_calls} alloc</span>
            <span className="item" style={{ color: result.stats.leak_count > 0 ? "#ffd1d1" : "#fff" }}>
              {result.stats.leak_count} leaks ({result.stats.leaked_bytes}B)
            </span>
          </>
        )}
        <div className="spacer" />
        <span className="item">PinTrace v1.0</span>
      </div>

      <SetupModal open={setupOpen} onClose={() => setSetupOpen(false)} />
    </div>
  );
}

function EditorWithJump({ value, onChange, language, markers, jumpRef }) {
  // Wrap MonacoEditor and expose a jump function via ref
  const editorRef = useRef(null);
  const monacoRef = useRef(null);
  React.useImperativeHandle(jumpRef, () => null); // no-op
  // expose via parent ref attribute
  useEffect(() => {
    jumpRef.current = (line) => {
      if (editorRef.current) {
        editorRef.current.revealLineInCenter(line);
        editorRef.current.setPosition({ lineNumber: line, column: 1 });
        editorRef.current.focus();
      }
    };
  }, [jumpRef]);

  return (
    <div style={{ minHeight: 0 }}>
      <MonacoEditorBridge
        value={value}
        onChange={onChange}
        language={language}
        markers={markers}
        editorRef={editorRef}
        monacoRef={monacoRef}
      />
    </div>
  );
}

// Bridge that captures editor instance into refs
function MonacoEditorBridge({ value, onChange, language, markers, editorRef, monacoRef }) {
  const [, setReady] = useState(0);
  return (
    <PatchedMonaco
      value={value}
      onChange={onChange}
      language={language}
      markers={markers}
      onReady={(ed, mon) => {
        editorRef.current = ed;
        monacoRef.current = mon;
        setReady((n) => n + 1);
      }}
    />
  );
}

function PatchedMonaco({ value, onChange, language, markers, onReady }) {
  // small wrapper that proxies onMount to give parent the editor instance
  return <MonacoEditor
    value={value}
    onChange={onChange}
    language={language}
    markers={markers}
    onMountExtra={onReady}
  />;
}

function Problems({ result, onJumpToLine }) {
  if (!result) {
    return <div className="empty" data-testid="problems-empty">Run the program — leaks will appear here as red squigglies in the editor.</div>;
  }
  const markers = result.markers || [];
  if (!markers.length) {
    return <div className="empty" data-testid="problems-clean" style={{ color: "#4ec9b0" }}>✓ No memory leaks detected</div>;
  }
  return (
    <div data-testid="problems-list">
      {markers.map((m, i) => (
        <div
          key={i}
          onClick={() => onJumpToLine && onJumpToLine(m.line)}
          style={{
            display: "flex", gap: 10, padding: "6px 8px",
            borderLeft: "3px solid var(--vsc-error)",
            background: "#2d1f1f", marginBottom: 4,
            cursor: "pointer", borderRadius: 2,
          }}
          data-testid={`problem-row-${i}`}
        >
          <AlertTriangle size={14} color="#f14c4c" style={{ marginTop: 2 }} />
          <div>
            <div style={{ color: "#f14c4c", fontWeight: 600 }}>Memory leak — {m.size} bytes</div>
            <div style={{ color: "var(--vsc-fg-muted)" }}>{m.message}</div>
            <div style={{ color: "var(--vsc-fg-muted)", fontSize: 11 }}>
  address {m.address}
</div>
          </div>
        </div>
      ))}
    </div>
  );
}