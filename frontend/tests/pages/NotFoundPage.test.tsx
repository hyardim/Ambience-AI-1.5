import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Routes, Route } from 'react-router-dom';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { renderWithProviders } from '@test/utils';

describe('NotFoundPage', () => {
  it('navigates back to home', async () => {
    const user = userEvent.setup();

    renderWithProviders(
      <Routes>
        <Route path="*" element={<NotFoundPage />} />
        <Route path="/" element={<div>Home Page</div>} />
      </Routes>,
      { routes: ['/missing'] },
    );

    await user.click(screen.getByRole('button', { name: /go to home/i }));

    expect(screen.getByText(/home page/i)).toBeInTheDocument();
  });
});
