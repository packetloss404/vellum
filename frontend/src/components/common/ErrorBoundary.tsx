import React from "react";
import { Button } from "./Button";

type ErrorBoundaryProps = {
  children: React.ReactNode;
};

type ErrorBoundaryState = {
  error: Error | null;
};

export default class ErrorBoundary extends React.Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(_error: Error, _info: React.ErrorInfo): void {
    // v1, localhost — React will surface the error in the console on its own.
  }

  handleReload = (): void => {
    window.location.reload();
  };

  render(): React.ReactNode {
    if (this.state.error) {
      return (
        <div className="min-h-screen flex items-center justify-center">
          <div className="max-w-prose p-12">
            <h1 className="font-serif text-2xl text-ink">
              The page lost its thread.
            </h1>
            <p className="font-serif text-ink-muted mt-4">
              The dossier will be here when you come back.
            </p>
            <Button
              type="button"
              onClick={this.handleReload}
              className="mt-8"
            >
              Reload
            </Button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
