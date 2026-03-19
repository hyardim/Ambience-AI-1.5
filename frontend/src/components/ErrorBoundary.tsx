import { Component, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: { componentStack: string }) {
    console.error('[ErrorBoundary] Uncaught error:', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-gray-50">
          <div className="max-w-md w-full bg-white rounded-lg shadow p-8 text-center">
            <div className="text-red-600 text-4xl mb-4">⚠</div>
            <h1 className="text-xl font-semibold text-gray-900 mb-2">Something went wrong</h1>
            <p className="text-gray-500 mb-6 text-sm">
              An unexpected error occurred. Please refresh the page or contact support if the problem persists.
            </p>
            {this.state.error && (
              <p className="text-xs text-gray-400 font-mono mb-6 break-all">
                {this.state.error.message}
              </p>
            )}
            <button
              onClick={() => window.location.reload()}
              className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 text-sm"
            >
              Reload page
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
