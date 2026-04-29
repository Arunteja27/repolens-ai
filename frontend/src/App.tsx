import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { EvalPage } from "./pages/EvalPage";
import { HomePage } from "./pages/HomePage";
import { RepoPage } from "./pages/RepoPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/repo/:repoId" element={<RepoPage />} />
        <Route path="/repo/:repoId/evals" element={<EvalPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

