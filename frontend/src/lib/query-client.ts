import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ApiError, errorMessage } from "./api";

const isNetworkish = (e: unknown) => e instanceof ApiError && (e.status === 0 || e.status >= 500);

/** Shared client so the chat runner (outside React) can update the same cache. */
export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error, query) => {
      if (query.meta?.silent) return;
      // Only surface background failures; first loads render their own error states.
      if (query.state.data !== undefined && isNetworkish(error)) {
        toast.error(errorMessage(error), { id: "network-error" });
      }
    },
  }),
  mutationCache: new MutationCache({
    onError: (error, _vars, _ctx, mutation) => {
      if (mutation.meta?.silent) return;
      if (error instanceof ApiError && error.status === 401) return;
      toast.error(errorMessage(error));
    },
  }),
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (count, error) => {
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
        return count < 2;
      },
    },
  },
});
