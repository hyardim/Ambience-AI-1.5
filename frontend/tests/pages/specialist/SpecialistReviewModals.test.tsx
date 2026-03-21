import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EditResponseModal } from '@/pages/specialist/SpecialistReviewModals';

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
