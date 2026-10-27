import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { AuthProvider } from "./lib/auth";
import { LanguageProvider } from "./lib/i18n";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={new QueryClient()}>
      <LanguageProvider><AuthProvider><BrowserRouter><App /></BrowserRouter></AuthProvider></LanguageProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
