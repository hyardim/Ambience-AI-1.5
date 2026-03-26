import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PatientContextBanner } from '@/components/PatientContextBanner';

describe('PatientContextBanner', () => {
  it('renders nothing when no context values are provided', () => {
    const { container } = render(<PatientContextBanner />);
    expect(container.firstChild).toBeNull();
  });

  it('renders chips and notes with title-cased values', () => {
    render(
      <PatientContextBanner
        age={42}
        sex="female"
        specialty="rheumatology"
        urgency="urgent"
        notes="Patient has persistent pain"
      />,
    );

    expect(screen.getByText(/patient context/i)).toBeInTheDocument();
    expect(screen.getByText('Age:')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText('Sex:')).toBeInTheDocument();
    expect(screen.getByText('Female')).toBeInTheDocument();
    expect(screen.getByText('Specialty:')).toBeInTheDocument();
    expect(screen.getByText('Rheumatology')).toBeInTheDocument();
    expect(screen.getByText('Urgency:')).toBeInTheDocument();
    expect(screen.getByText('Urgent')).toBeInTheDocument();
    expect(screen.getByText('Notes:')).toBeInTheDocument();
    expect(screen.getByText(/patient has persistent pain/i)).toBeInTheDocument();
  });
});
