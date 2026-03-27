import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { PasswordStrengthMeter } from '@/components/PasswordStrengthMeter';
import { renderWithProviders } from '@test/utils';

describe('PasswordStrengthMeter', () => {
  it('renders nothing for an empty password', () => {
    const { container } = renderWithProviders(<PasswordStrengthMeter password="" />, {
      withAuth: false,
    });
    expect(container).toBeEmptyDOMElement();
  });

  it('shows all strength rules and marks passing ones', () => {
    renderWithProviders(<PasswordStrengthMeter password="Strong1!" />, { withAuth: false });

    expect(screen.getByText('8+ characters')).toBeInTheDocument();
    expect(screen.getByText('Uppercase letter')).toBeInTheDocument();
    expect(screen.getByText('Lowercase letter')).toBeInTheDocument();
    expect(screen.getByText('Number')).toBeInTheDocument();
    expect(screen.getByText('Special character')).toBeInTheDocument();
    expect(screen.getAllByText('✓')).toHaveLength(5);
  });
});
