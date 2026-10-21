import "./index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import Layout from "./components/Layout";
import { Jobs, Suppressions } from "./pages/Admin";
import Followups from "./pages/Followups";
import LeadDetail from "./pages/LeadDetail";
import Leads from "./pages/Leads";
import Overview from "./pages/Overview";
import ReviewQueue from "./pages/ReviewQueue";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 10_000, refetchOnWindowFocus: true, retry: 1 } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Overview />} />
            <Route path="leads" element={<Leads />} />
            <Route path="leads/:id" element={<LeadDetail />} />
            <Route path="review" element={<ReviewQueue />} />
            <Route path="followups" element={<Followups />} />
            <Route path="suppressions" element={<Suppressions />} />
            <Route path="jobs" element={<Jobs />} />
            <Route path="*" element={<p className="text-sm text-slate-500">Page not found.</p>} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
