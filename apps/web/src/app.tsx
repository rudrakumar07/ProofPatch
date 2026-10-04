import { Link, Route, Routes } from "react-router-dom";
import NewRunPage from "./pages/NewRunPage";
import RunPage from "./pages/RunPage";

export default function App() {
  return (
    <div className="app">
      <header className="app-header">
        <Link to="/" className="brand">
          ProofPatch
        </Link>
        <span className="tagline">AI proposes · tooling executes · evidence compares</span>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<NewRunPage />} />
          <Route path="/runs/:runId" element={<RunPage />} />
        </Routes>
      </main>
      <footer className="app-footer">
        <span>
          ProofPatch v0.1 reports <strong>evidence</strong>, not proof of correctness. Verification
          commands execute local repository code — use only repositories you trust.
        </span>
      </footer>
    </div>
  );
}
