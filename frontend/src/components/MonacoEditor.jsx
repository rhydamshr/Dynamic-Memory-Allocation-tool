import React, { useEffect, useRef } from "react";
import Editor, { loader } from "@monaco-editor/react";

// Configure VS Code Dark+ theme
loader.init().then((monaco) => {
  monaco.editor.defineTheme("pintrace-dark", {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "comment", foreground: "6A9955", fontStyle: "italic" },
      { token: "keyword", foreground: "569CD6" },
      { token: "string", foreground: "CE9178" },
      { token: "number", foreground: "B5CEA8" },
      { token: "type", foreground: "4EC9B0" },
      { token: "identifier", foreground: "9CDCFE" },
      { token: "delimiter", foreground: "D4D4D4" },
    ],
    colors: {
      "editor.background": "#1e1e1e",
      "editor.foreground": "#d4d4d4",
      "editorLineNumber.foreground": "#858585",
      "editorLineNumber.activeForeground": "#c6c6c6",
      "editor.selectionBackground": "#264f78",
      "editor.lineHighlightBackground": "#2a2d2e",
      "editorCursor.foreground": "#aeafad",
      "editorIndentGuide.background": "#404040",
      "editorWhitespace.foreground": "#3b3b3b",
      "editorWidget.background": "#252526",
      "editorWidget.border": "#454545",
      "editorMarkerNavigationError.background": "#f14c4c",
      "editorMarkerNavigationWarning.background": "#cca700",
    },
  });
});

export default function MonacoEditor({ value, onChange, language = "c", markers = [], onMountExtra }) {

  const editorRef = useRef(null);
  const monacoRef = useRef(null);

  function handleMount(editor, monaco) {
    editorRef.current = editor;
    monacoRef.current = monaco;
    monaco.editor.setTheme("pintrace-dark");
    applyMarkers(markers, editor, monaco);
    if (onMountExtra) onMountExtra(editor, monaco);
  }

  function applyMarkers(ms, editor, monaco) {
    if (!editor || !monaco) return;
    const model = editor.getModel();
    if (!model) return;
    const owner = "pintrace-leaks";
    const monacoMarkers = ms.map((m) => ({
      severity:
        m.severity === "error"
          ? monaco.MarkerSeverity.Error
          : m.severity === "warning"
          ? monaco.MarkerSeverity.Warning
          : monaco.MarkerSeverity.Info,
      message: m.message,
      startLineNumber: m.line,
      startColumn: m.col,
      endLineNumber: m.end_line,
      endColumn: m.end_col,
      source: "PinTrace",
    }));
    monaco.editor.setModelMarkers(model, owner, monacoMarkers);
  }

  useEffect(() => {
    if (editorRef.current && monacoRef.current) {
      applyMarkers(markers, editorRef.current, monacoRef.current);
    }
  }, [markers]);

  return (
    <div data-testid="monaco-editor-wrap" style={{ height: "100%", width: "100%" }}>
      <Editor
        height="100%"
        language={language}
        theme="pintrace-dark"
        value={value}
        onChange={(v) => onChange(v ?? "")}
        onMount={handleMount}
        options={{
          fontFamily: "'Cascadia Code', 'JetBrains Mono', Consolas, monospace",
          fontSize: 13,
          minimap: { enabled: true },
          smoothScrolling: true,
          cursorSmoothCaretAnimation: "on",
          scrollBeyondLastLine: false,
          automaticLayout: true,
          renderLineHighlight: "all",
          tabSize: 4,
          glyphMargin: true,
          fixedOverflowWidgets: true,
        }}
      />
    </div>
  );
}