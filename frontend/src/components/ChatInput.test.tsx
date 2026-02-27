import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatInput } from './ChatInput';

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
});
