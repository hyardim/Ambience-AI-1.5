import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EditResponseModal, ManualResponseModal } from '@/pages/specialist/SpecialistReviewModals';

describe('EditResponseModal', () => {
  const defaultProps = {
    open: true,
    actionLoading: false,
    editedContent: 'Some AI response',
    editedSources: '',
    feedback: '',
    onContentChange: vi.fn(),
    onSourcesChange: vi.fn(),
    onFeedbackChange: vi.fn(),
    onCancel: vi.fn(),
    onConfirm: vi.fn(),
  };

  it('renders nothing when closed', () => {
    const { container } = render(
      <EditResponseModal {...defaultProps} open={false} />,
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders modal content when open', () => {
    render(<EditResponseModal {...defaultProps} />);

    expect(screen.getByText(/edit response/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/edit the response/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/optional. add one source per line/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/optional. explain what you changed/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /save edited response/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
  });

  it('calls onContentChange, onSourcesChange, and onFeedbackChange on input', async () => {
    const onContentChange = vi.fn();
    const onSourcesChange = vi.fn();
    const onFeedbackChange = vi.fn();
    render(
      <EditResponseModal
        {...defaultProps}
        editedContent=""
        onContentChange={onContentChange}
        onSourcesChange={onSourcesChange}
        onFeedbackChange={onFeedbackChange}
      />,
    );
    const user = userEvent.setup();

    await user.type(screen.getByPlaceholderText(/edit the response/i), 'a');
    expect(onContentChange).toHaveBeenCalled();

    await user.type(screen.getByPlaceholderText(/optional. add one source per line/i), 'b');
    expect(onSourcesChange).toHaveBeenCalled();

    await user.type(screen.getByPlaceholderText(/optional. explain what you changed/i), 'c');
    expect(onFeedbackChange).toHaveBeenCalled();
  });

  it('disables save button when content is empty', () => {
    render(<EditResponseModal {...defaultProps} editedContent="" />);

    expect(screen.getByRole('button', { name: /save edited response/i })).toBeDisabled();
  });

  it('disables save button when content is whitespace only', () => {
    render(<EditResponseModal {...defaultProps} editedContent="   " />);

    expect(screen.getByRole('button', { name: /save edited response/i })).toBeDisabled();
  });

  it('enables save button when content has text', () => {
    render(<EditResponseModal {...defaultProps} editedContent="Valid content" />);

    expect(screen.getByRole('button', { name: /save edited response/i })).toBeEnabled();
  });

  it('calls onConfirm when save button is clicked', async () => {
    const onConfirm = vi.fn();
    render(<EditResponseModal {...defaultProps} onConfirm={onConfirm} />);
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: /save edited response/i }));

    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it('calls onCancel when cancel button is clicked', async () => {
    const onCancel = vi.fn();
    render(<EditResponseModal {...defaultProps} onCancel={onCancel} />);
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(onCancel).toHaveBeenCalledOnce();
  });

  it('shows loading text when actionLoading is true', () => {
    render(<EditResponseModal {...defaultProps} actionLoading />);

    expect(screen.getByRole('button', { name: /saving/i })).toBeDisabled();
  });
});

describe('ManualResponseModal', () => {
  const defaultProps = {
    open: true,
    actionLoading: false,
    manualResponseContent: '',
    manualResponseSources: '',
    manualResponseFiles: [],
    onContentChange: vi.fn(),
    onSourcesChange: vi.fn(),
    onFilesChange: vi.fn(),
    onCancel: vi.fn(),
    onConfirm: vi.fn(),
  };

  it('renders selected files and blocks oversized attachments', async () => {
    const onFilesChange = vi.fn();
    render(
      <ManualResponseModal
        {...defaultProps}
        manualResponseContent="Use this instead"
        manualResponseFiles={[new File(['ok'], 'source.txt', { type: 'text/plain' })]}
        onFilesChange={onFilesChange}
      />,
    );

    expect(screen.getByText('source.txt')).toBeInTheDocument();

    const user = userEvent.setup({ applyAccept: false });
    const fileInput = screen.getByText(/attach files/i).parentElement?.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(
      fileInput,
      new File(['x'.repeat(11 * 1024 * 1024)], 'too-large.pdf', { type: 'application/pdf' }),
    );

    expect(screen.getByText(/file\(s\) exceed the 3 mb limit/i)).toBeInTheDocument();
    expect(onFilesChange).not.toHaveBeenCalled();
  });
});
