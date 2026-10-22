import { Component, type ErrorInfo, type ReactNode } from "react";
import { RotateCcw, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  children: ReactNode;
  /** Changing this (e.g. the pathname) clears a caught error. */
  resetKey?: string;
}

interface State {
  error: Error | null;
  resetKey?: string;
}

/** Last line of defence: a render crash shows a recoverable screen instead of a blank page. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, resetKey: this.props.resetKey };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    return props.resetKey !== state.resetKey ? { error: null, resetKey: props.resetKey } : null;
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Sphura UI error:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="grid min-h-dvh place-items-center bg-background px-6 text-center">
        <div className="max-w-sm">
          <div className="mx-auto grid size-11 place-items-center rounded-xl border bg-card text-warning">
            <TriangleAlert className="size-5" strokeWidth={1.75} />
          </div>
          <h1 className="mt-4 font-brand text-2xl font-normal">Something went wrong</h1>
          <p className="mt-2 text-sm break-words text-muted-foreground">{this.state.error.message || "Unexpected error."}</p>
          <div className="mt-6 flex justify-center gap-2">
            <Button variant="outline" onClick={() => this.setState({ error: null })}>
              Try again
            </Button>
            <Button onClick={() => window.location.assign("/")}>
              <RotateCcw /> Reload
            </Button>
          </div>
        </div>
      </div>
    );
  }
}
