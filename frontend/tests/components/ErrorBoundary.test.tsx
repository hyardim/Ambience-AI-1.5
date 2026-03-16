import { Component } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, afterEach } from 'vitest';
import { ErrorBoundary } from '@/components/ErrorBoundary';

class Boom extends Component<{ shouldThrow?: boolean }> {
  render() {
    if (this.props.shouldThrow) {
      throw new Error('kaboom');
    }

    return <div>safe child</div>;
  }
}

describe('ErrorBoundary', () => {
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

  afterEach(() => {
    consoleError.mockClear();
  });

  it('renders children when there is no error', () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );

    expect(screen.getByText('safe child')).toBeInTheDocument();
  });

  it('renders the default fallback when a child throws', () => {
    render(
      <ErrorBoundary>
        <Boom shouldThrow />
      </ErrorBoundary>,
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByText('kaboom')).toBeInTheDocument();
    expect(consoleError).toHaveBeenCalled();
  });

  it('renders a custom fallback when provided', () => {
    render(
      <ErrorBoundary fallback={<div>custom fallback</div>}>
        <Boom shouldThrow />
      </ErrorBoundary>,
    );

    expect(screen.getByText('custom fallback')).toBeInTheDocument();
  });

  it('resets internal error state when handleReset is called', () => {
    const boundary = new ErrorBoundary({ children: <div>child</div> });
    const setState = vi.fn();
    boundary.setState = setState as typeof boundary.setState;

    boundary.handleReset();

    expect(setState).toHaveBeenCalledWith({ hasError: false, error: null });
  });

  it('reloads the page when reload is clicked', async () => {
    const user = userEvent.setup();
    const reload = vi.fn();
    const originalLocation = window.location;
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...originalLocation, reload },
    });

    render(
      <ErrorBoundary>
        <Boom shouldThrow />
      </ErrorBoundary>,
    );

    await user.click(screen.getByRole('button', { name: /reload page/i }));

    expect(reload).toHaveBeenCalledOnce();

    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    });
  });
});
