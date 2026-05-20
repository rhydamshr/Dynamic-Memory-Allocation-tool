import React from "react";
import IDE from "./components/IDE";
import "./App.css";

export default function App() {
  return (
    <div className="App pintrace-root" data-testid="pintrace-app-root">
      <IDE />
    </div>
  );
}
