"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { MotionConfig } from "framer-motion";
import { useState } from "react";
import { Toaster } from "sonner";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { staleTime: 15_000, refetchOnWindowFocus: false, retry: 1 } },
      }),
  );
  return (
    <QueryClientProvider client={client}>
        <MotionConfig reducedMotion="user" transition={{ type: "spring", stiffness: 380, damping: 34 }}>
          <TooltipPrimitive.Provider delayDuration={200}>
            {children}
            <Toaster
              position="bottom-right"
              theme="light"
              toastOptions={{
                classNames: {
                  toast: "!bg-surface !border-line !text-ink !shadow-pop !rounded-xl",
                  description: "!text-ink-2",
                  actionButton: "!bg-accent !text-white",
                },
              }}
            />
          </TooltipPrimitive.Provider>
        </MotionConfig>
    </QueryClientProvider>
  );
}
