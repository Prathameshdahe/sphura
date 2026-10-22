import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "framer-motion";
import { ThemeProvider } from "next-themes";
import "@fontsource-variable/hanken-grotesk";
import "@fontsource-variable/nunito";
import "@fontsource-variable/source-serif-4";
import "@fontsource-variable/source-serif-4/wght-italic.css";
import "@fontsource-variable/jetbrains-mono";
import "katex/dist/katex.min.css";
import "./index.css";
import App from "./App";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { queryClient } from "@/lib/query-client";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      {/* index.html applies the theme before paint; the provider's inline script is inert in an SPA (typed as data to keep React 19 quiet). */}
      <ThemeProvider
        attribute="class"
        defaultTheme="light"
        enableSystem
        disableTransitionOnChange
        scriptProps={{ type: "application/json" }}
      >
        <TooltipProvider delayDuration={350}>
          <MotionConfig reducedMotion="user">
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </MotionConfig>
          <Toaster position="top-center" closeButton />
        </TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
);
