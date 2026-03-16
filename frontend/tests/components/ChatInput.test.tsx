import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatInput } from '@/components/ChatInput';

describe('ChatInput', () => {
  it('renders the input and send button', () => {
    render(<ChatInput onSendMessage={vi.fn()} />);

    expect(screen.getByPlaceholderText(/type your message/i)).toBeInTheDocument();
  });

  it('calls onSendMessage with the message text', async () => {
    const onSend = vi.fn();
    render(<ChatInput onSendMessage={onSend} />);
    const user = userEvent.setup();

    await user.type(screen.getByPlaceholderText(/type your message/i), 'Hello doctor');
    // Find the submit button by type attribute (icon-only buttons have no accessible name)
    const buttons = screen.getAllByRole('button');
    const submitBtn = buttons.find(b => b.getAttribute('type') === 'submit');
    expect(submitBtn).toBeDefined();

    await user.click(submitBtn!);

    expect(onSend).toHaveBeenCalledWith('Hello doctor', []);
  });

  it('does not call onSendMessage when input is empty', async () => {
    const onSend = vi.fn();
    render(<ChatInput onSendMessage={onSend} />);
    const user = userEvent.setup();

    const buttons = screen.getAllByRole('button');
    const submitBtn = buttons.find(b => b.getAttribute('type') === 'submit');
    await user.click(submitBtn!);

    expect(onSend).not.toHaveBeenCalled();
  });

  it('clears input after sending', async () => {
    const onSend = vi.fn();
    render(<ChatInput onSendMessage={onSend} />);
    const user = userEvent.setup();

    const input = screen.getByPlaceholderText(/type your message/i);
    await user.type(input, 'Test message');
    const submitBtn = screen.getAllByRole('button').find(b => b.getAttribute('type') === 'submit');
    await user.click(submitBtn!);

    expect(input).toHaveValue('');
  });

  it('disables input when disabled prop is true', () => {
    render(<ChatInput onSendMessage={vi.fn()} disabled />);

    expect(screen.getByPlaceholderText(/type your message/i)).toBeDisabled();
  });

  it('uses custom placeholder text', () => {
    render(<ChatInput onSendMessage={vi.fn()} placeholder="Custom placeholder" />);

    expect(screen.getByPlaceholderText('Custom placeholder')).toBeInTheDocument();
  });

  it('uploads, removes, and submits attached files', async () => {
    const onSend = vi.fn();
    render(<ChatInput onSendMessage={onSend} />);
    const user = userEvent.setup({ applyAccept: false });

    const input = document.getElementById('chat-file-input') as HTMLInputElement;
    expect(input).toHaveAttribute('accept', '.pdf,.txt,.md,.rtf,.doc,.docx,.csv,.json,.xml');
    const file = new File(['hello'], 'note.txt', { type: 'text/plain' });
    await user.upload(input, file);

    expect(screen.getByText('note.txt')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '×' }));
    expect(screen.queryByText('note.txt')).not.toBeInTheDocument();

    await user.upload(input, file);
    const submitBtn = screen.getAllByRole('button').find(b => b.getAttribute('type') === 'submit');
    await user.click(submitBtn!);

    expect(onSend).toHaveBeenCalledWith('', [file]);
    expect(screen.queryByText('note.txt')).not.toBeInTheDocument();
  });

  it('does not add files when the chooser is cancelled and disables attachment controls', async () => {
    render(<ChatInput onSendMessage={vi.fn()} disabled />);
    const user = userEvent.setup({ applyAccept: false });

    const input = document.getElementById('chat-file-input') as HTMLInputElement;
    await user.upload(input, []);

    expect(screen.queryByText(/\.txt$/i)).not.toBeInTheDocument();
    expect(screen.getAllByRole('button').find((button) => button.getAttribute('type') === 'submit')).toBeDisabled();
    expect(document.querySelector('label[for="chat-file-input"]')).toHaveAttribute('aria-disabled', 'true');
  });

  it('submits whitespace messages when files are attached and ignores empty file selections', async () => {
    const onSend = vi.fn();
    render(<ChatInput onSendMessage={onSend} />);
    const user = userEvent.setup({ applyAccept: false });
    const input = document.getElementById('chat-file-input') as HTMLInputElement;
    const file = new File(['hello'], 'note.txt', { type: 'text/plain' });

    await user.upload(input, []);
    await user.upload(input, file);
    await user.type(screen.getByPlaceholderText(/type your message/i), '   ');
    await user.click(screen.getAllByRole('button').find((button) => button.getAttribute('type') === 'submit')!);

    expect(onSend).toHaveBeenCalledWith('   ', [file]);
  });

  it('ignores file change events with a null file list', () => {
    render(<ChatInput onSendMessage={vi.fn()} />);
    const input = document.getElementById('chat-file-input') as HTMLInputElement;

    fireEvent.change(input, { target: { files: null } });

    expect(screen.queryByText(/note\.txt/i)).not.toBeInTheDocument();
  });
});
