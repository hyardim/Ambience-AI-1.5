import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatMessage } from '@/components/ChatMessage';
import type { Message } from '@/types';

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

  it('does not apply AI review styling to human messages', () => {
    const { container } = render(<ChatMessage message={baseMessage} />);
    expect(container.querySelector('.border-l-4')).toBeNull();
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
      attachments: [{ id: 'f1', name: 'report.pdf', size: '2MB', type: 'pdf' }],
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

  it('renders streamed AI content while generation is still in progress', () => {
    const streamingAiMessage: Message = {
      ...baseMessage,
      senderType: 'ai',
      senderName: 'AI',
      content: 'Partial streamed answer',
      isGenerating: true,
    };

    render(<ChatMessage message={streamingAiMessage} />);

    expect(screen.getByText('Partial streamed answer')).toBeInTheDocument();
  });

  it('renders citations with pages, sections, and dates', () => {
    const aiMessage: Message = {
      ...baseMessage,
      senderType: 'ai',
      citations: [
        {
          doc_id: 'doc-1',
          title: 'Guideline A',
          source_name: 'NICE',
          page_start: 3,
          page_end: 5,
          section_path: ['Section 1', 'Subsection A'],
          publish_date: '2024-01-01',
        },
      ],
    };

    render(<ChatMessage message={aiMessage} />);

    expect(screen.getByText(/sources/i)).toBeInTheDocument();
    expect(screen.getByText(/guideline a/i)).toBeInTheDocument();
    expect(screen.getByText(/nice • pages 3-5 • section 1 > subsection a/i)).toBeInTheDocument();
    expect(screen.getByText(/published 2024-01-01/i)).toBeInTheDocument();
  });

  it('prefers in-app document links over absolute source URLs', () => {
    const aiMessage: Message = {
      ...baseMessage,
      senderType: 'ai',
      citations: [
        {
          title: 'Guideline A',
          source_name: 'NICE',
          document_url: '/documents/doc-1',
          source_url: 'https://www.nice.org.uk',
          page_start: 3,
        },
      ],
    };

    render(<ChatMessage message={aiMessage} />);

    expect(screen.getByRole('link', { name: 'Guideline A' })).toHaveAttribute(
      'href',
      '/documents/doc-1#page=3',
    );
  });

  it('uses in-app document links when source URLs are not absolute', () => {
    const aiMessage: Message = {
      ...baseMessage,
      senderType: 'ai',
      citations: [
        {
          title: 'Guideline A',
          source_name: 'NICE',
          document_url: '/documents/doc-1',
          source_url: '/docs/doc-1',
          page_start: 3,
        },
      ],
    };

    render(<ChatMessage message={aiMessage} />);

    expect(screen.getByRole('link', { name: 'Guideline A' })).toHaveAttribute(
      'href',
      '/documents/doc-1#page=3',
    );
  });

  it('renders page zero citations when the page number is explicitly zero', () => {
    const aiMessage: Message = {
      ...baseMessage,
      senderType: 'ai',
      citations: [
        {
          title: 'Guideline Zero',
          source_name: 'NICE',
          page_start: 0,
        },
      ],
    };

    render(<ChatMessage message={aiMessage} />);

    expect(screen.getByText(/nice • page 0/i)).toBeInTheDocument();
  });

  it('renders fallback citation variants and human timestamps', () => {
    const olderAiMessage: Message = {
      ...baseMessage,
      senderType: 'ai',
      timestamp: new Date('2024-01-15T10:00:00Z'),
      citations: [
        {
          title: 'Guideline B',
          source_name: 'BSR',
          page_start: 7,
          section_path: 'Appendix',
          last_updated_date: '2024-02-01',
        },
        {
          title: 'Guideline C',
          source_name: 'NICE',
          creation_date: '2023-01-01',
        },
      ],
    };

    render(<ChatMessage message={olderAiMessage} />);

    expect(screen.getByText(/sent 15\/01\/2024 at/i)).toBeInTheDocument();
    expect(screen.getByText(/bsr • page 7 • appendix/i)).toBeInTheDocument();
    expect(screen.getByText(/updated 2024-02-01/i)).toBeInTheDocument();
    expect(screen.getByText(/created 2023-01-01/i)).toBeInTheDocument();
    expect(screen.getByText('Guideline C')).toBeInTheDocument();
  });

  it('falls back to "Unknown time" when timestamp cannot be parsed', () => {
    const invalidTimestampMessage: Message = {
      ...baseMessage,
      timestamp: { bad: true } as unknown as Date,
    };

    render(<ChatMessage message={invalidTimestampMessage} />);

    expect(screen.getByText(/unknown time/i)).toBeInTheDocument();
  });

  it('accepts ISO timestamp strings and formats them safely', () => {
    const stringTimestampMessage: Message = {
      ...baseMessage,
      timestamp: '2024-01-20T09:30:00Z' as unknown as Date,
    };

    render(<ChatMessage message={stringTimestampMessage} />);

    expect(screen.getByText(/sent 20\/01\/2024 at/i)).toBeInTheDocument();
  });

  it('falls back when a string timestamp cannot be parsed', () => {
    const invalidStringTimestampMessage: Message = {
      ...baseMessage,
      timestamp: 'not-a-date' as unknown as Date,
    };

    render(<ChatMessage message={invalidStringTimestampMessage} />);

    expect(screen.getByText(/unknown time/i)).toBeInTheDocument();
  });

  it('renders citations without document dates or document links', () => {
    const aiMessage: Message = {
      ...baseMessage,
      senderType: 'ai',
      citations: [
        {
          title: 'Guideline D',
          source_name: 'NICE',
        },
      ],
    };

    render(<ChatMessage message={aiMessage} />);

    expect(screen.getByText('Guideline D').tagName).toBe('SPAN');
    expect(screen.queryByText(/published|updated|created/i)).not.toBeInTheDocument();
  });

  it('renders manual URL sources as clickable links that open in a new tab', () => {
    // Simulates a specialist manual response citation where the source is a URL
    const specialistMsg: Message = {
      ...baseMessage,
      senderType: 'specialist',
      senderName: 'Dr Specialist',
      content: 'Use the NICE guideline.',
      citations: [
        {
          title: 'https://nice.org.uk/guidance/ng228',
          source_name: 'Manual source',
          source_url: 'https://nice.org.uk/guidance/ng228',
        },
        {
          title: 'NICE NG228',
          source_name: 'Manual source',
        },
        {
          title: 'uploaded-file.pdf',
          source_name: 'Manual source',
          source_url: '/chats/1/files/5',
        },
      ],
    };

    render(<ChatMessage message={specialistMsg} />);

    // URL source → clickable link opening in new tab
    const urlLink = screen.getByRole('link', { name: 'https://nice.org.uk/guidance/ng228' });
    expect(urlLink).toHaveAttribute('href', 'https://nice.org.uk/guidance/ng228');
    expect(urlLink).toHaveAttribute('target', '_blank');

    // Plain text source → not a link
    expect(screen.getByText('NICE NG228').tagName).toBe('SPAN');

    // Uploaded file source → clickable link to download
    const fileLink = screen.getByRole('link', { name: 'uploaded-file.pdf' });
    expect(fileLink).toHaveAttribute('href', '/chats/1/files/5');
    expect(fileLink).toHaveAttribute('target', '_blank');
  });

  it('falls back to a generic source label in linked and unlinked citations', () => {
    const aiMessage: Message = {
      ...baseMessage,
      senderType: 'ai',
      citations: [
        { doc_id: 'doc-1', source_name: 'NICE', source_url: 'https://example.com/doc.pdf' },
        { source_name: 'NICE' },
      ],
    };

    render(<ChatMessage message={aiMessage} />);

    expect(screen.getAllByText('Source')).toHaveLength(2);
    expect(screen.getByRole('link', { name: 'Source' })).toHaveAttribute(
      'href',
      'https://example.com/doc.pdf',
    );
  });

  it('renders review badges, feedback, and specialist actions', async () => {
    const user = userEvent.setup();
    const approve = vi.fn();
    const approveWithComment = vi.fn();
    const requestChanges = vi.fn();
    const manualResponse = vi.fn();

    const reviewedMessage: Message = {
      ...baseMessage,
      senderType: 'ai',
      reviewStatus: 'rejected',
      reviewFeedback: 'Please cite the guideline.',
    };

    const { rerender } = render(
      <ChatMessage
        message={reviewedMessage}
        showReviewStatus
        showReviewActions
        onApprove={approve}
        onApproveWithComment={approveWithComment}
        onRequestChanges={requestChanges}
        onManualResponse={manualResponse}
      />,
    );

    expect(screen.getByText(/changes requested/i)).toBeInTheDocument();
    expect(screen.getByText(/specialist feedback/i)).toBeInTheDocument();
    expect(screen.getByText(/please cite the guideline/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /^Approve$/i }));
    await user.click(screen.getByRole('button', { name: /^Approve with Comment$/i }));
    await user.click(screen.getByRole('button', { name: /^Request Changes$/i }));
    await user.click(screen.getByRole('button', { name: /^Manual Response$/i }));

    expect(approve).toHaveBeenCalled();
    expect(approveWithComment).toHaveBeenCalled();
    expect(requestChanges).toHaveBeenCalled();
    expect(manualResponse).toHaveBeenCalled();

    rerender(
      <ChatMessage message={{ ...reviewedMessage, reviewStatus: 'approved' }} showReviewStatus />,
    );
    expect(screen.getByText(/specialist approved/i)).toBeInTheDocument();

    rerender(
      <ChatMessage message={{ ...reviewedMessage, reviewStatus: 'replaced' }} showReviewStatus />,
    );
    expect(screen.getByText(/replaced by specialist/i)).toBeInTheDocument();

    rerender(
      <ChatMessage
        message={{ ...reviewedMessage, reviewStatus: undefined, isGenerating: true }}
        showReviewStatus
      />,
    );
    expect(screen.getByText(/generating/i)).toBeInTheDocument();

    rerender(
      <ChatMessage
        message={{ ...reviewedMessage, reviewStatus: undefined, isGenerating: false }}
        showReviewStatus
      />,
    );
    expect(screen.getByText(/awaiting review/i)).toBeInTheDocument();
  });
});
