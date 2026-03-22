import { describe, it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { render } from '@testing-library/react';
import App from './App';

describe('App routing smoke', () => {
  it('renders landing page at root', async () => {
    window.history.pushState({}, '', '/');
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/NHS Ambience AI 1.5/i)).toBeInTheDocument();
    });
  });
});
