import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ChatMessage } from './ChatMessage';
import type { Message } from '../types';

const baseMessage: Message = {
  id: '1',
  senderId: 'user-1',
  senderName: 'Dr Smith',
  senderType: 'gp',
  content: 'Patient presents with headache',
  timestamp: new Date('2025-01-15T10:00:00Z'),
};

describe('ChatMessage', () => {
  it('renders message content', () => {
    render(<ChatMessage message={baseMessage} />);
    expect(screen.getByText('Patient presents with headache')).toBeInTheDocument();
  });

  it('renders sender name for human messages', () => {
    render(<ChatMessage message={baseMessage} />);
    expect(screen.getByText('Dr Smith')).toBeInTheDocument();
  });

  it('renders "NHS AI Assistant" for AI messages', () => {
    const aiMessage: Message = {
      ...baseMessage,
      senderType: 'ai',
      senderName: 'AI',
    };
    render(<ChatMessage message={aiMessage} />);
    expect(screen.getByText('NHS AI Assistant')).toBeInTheDocument();
  });

  it('renders attachments when present', () => {
    const msgWithAttachments: Message = {
      ...baseMessage,
      attachments: [
        { id: 'f1', name: 'report.pdf', size: '2MB', type: 'pdf' },
      ],
    };
    render(<ChatMessage message={msgWithAttachments} />);
    expect(screen.getByText('report.pdf')).toBeInTheDocument();
    expect(screen.getByText('2MB')).toBeInTheDocument();
  });

  it('renders guideline reference when present', () => {
    const msgWithGuideline: Message = {
      ...baseMessage,
      guidelineReference: {
        title: 'NICE Guideline NG188',
        referenceNo: 'NG188',
        lastUpdated: 'January 2024',
      },
    };
    render(<ChatMessage message={msgWithGuideline} />);
    expect(screen.getByText('NICE Guideline NG188')).toBeInTheDocument();
    // NG188 appears in both the title and ref number, so use getAllByText
    expect(screen.getAllByText(/NG188/).length).toBeGreaterThanOrEqual(2);
  });

  it('applies own-message styling when isOwnMessage is true', () => {
    const { container } = render(<ChatMessage message={baseMessage} isOwnMessage />);
    // The top-level flex div should have flex-row-reverse class
    const wrapper = container.firstElementChild;
    expect(wrapper?.className).toContain('flex-row-reverse');
  });
});
