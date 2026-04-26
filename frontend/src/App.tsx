import React, { Suspense } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ErrorBoundary from "./components/common/ErrorBoundary";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
    },
  },
});

const DossierListPage = React.lazy(() => import("./pages/DossierListPage"));
const IntakePage = React.lazy(() => import("./pages/IntakePage"));
const DossierPage = React.lazy(() => import("./pages/DossierPage"));
const DemoPage = React.lazy(() => import("./pages/DemoPage"));
const StressPage = React.lazy(() => import("./pages/StressPage"));
const Stress2Page = React.lazy(() => import("./pages/Stress2Page"));
const Stress3Page = React.lazy(() => import("./pages/Stress3Page"));
const Stress4Page = React.lazy(() => import("./pages/Stress4Page"));
const SettingsPage = React.lazy(() => import("./pages/SettingsPage"));
const NotFoundPage = React.lazy(() => import("./pages/NotFoundPage"));

const LoadingFallback = () => (
  <div className="p-12 text-ink-faint">Loading…</div>
);

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Suspense fallback={<LoadingFallback />}>
          <ErrorBoundary>
            <Routes>
              <Route path="/" element={<DossierListPage />} />
              <Route path="/intake" element={<IntakePage />} />
              <Route path="/intake/:id" element={<IntakePage />} />
              <Route path="/dossiers/:id" element={<DossierPage />} />
              <Route path="/demo" element={<DemoPage />} />
              <Route path="/stress" element={<StressPage />} />
              <Route path="/stress2" element={<Stress2Page />} />
              <Route path="/stress3" element={<Stress3Page />} />
              <Route path="/stress4" element={<Stress4Page />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </ErrorBoundary>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
