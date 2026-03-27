import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import { GPQueryDetailPage } from '@/pages/gp/GPQueryDetailPage';
import { shouldAutoConnectGpStream } from '@/utils/gpDetail';
import { renderWithProviders, seedAuth } from '@test/utils';
import { server } from '@test/mocks/server';
import { mockChatWithMessages } from '@test/mocks/handlers';
import type { Message } from '@/types';
import * as api from '@/services/api';

const mockConnectStream = vi.fn(() => Promise.resolve());
const mockStartPolling = vi.fn();
const mockStopPolling = vi.fn();
let latestOnRefresh: (() => Promise<void>) | null = null;
let latestOnFileContextTruncated: (() => void) | null = null;
const hookState = {
  phase: 'idle' as 'idle' | 'connecting' | 'streaming' | 'completed' | 'fallback_polling',
  isStreaming: false,
  injectPlaceholder: false,
  injectStringTimestamp: false,
  stripGeneratingPlaceholders: false,
};

vi.mock('@/hooks/useChatStream', () => ({
  useChatStream: (
    setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
    options: { onRefresh: () => Promise<void>; onFileContextTruncated?: () => void },
  ) => {
    latestOnRefresh = options.onRefresh;
    latestOnFileContextTruncated = options.onFileContextTruncated ?? null;
    return {
      phase: hookState.phase,
      isStreaming: hookState.isStreaming,
      connectStream: (chatId: number) => {
        if (hookState.stripGeneratingPlaceholders) {
          setMessages((prev) => prev.filter((m) => !(m.senderType === 'ai' && m.isGenerating)));
        }
        if (hookState.injectPlaceholder) {
          setMessages((prev) => [
            ...prev,
            {
              id: '999',
              senderId: 'ai',
              senderName: 'NHS AI Assistant',
              senderType: 'ai',
              content: '',
              timestamp: new Date(),
              isGenerating: true,
            },
          ]);
        }
        if (hookState.injectStringTimestamp) {
          setMessages((prev) => [
            ...prev,
            {
              id: '998',
              senderId: 'ai',
              senderName: 'NHS AI Assistant',
              senderType: 'ai',
              content: 'String timestamp message',
              timestamp: '2025-01-15T10:02:00Z' as unknown as Date,
              isGenerating: false,
            },
          ]);
        }
        return mockConnectStream(chatId);
      },
      startPolling: mockStartPolling,
      stopPolling: mockStopPolling,
    };
  },
}));

vi.mock('@/components/ChatInput', () => ({
  ChatInput: ({
    onSendMessage,
    disabled,
  }: {
    onSendMessage: (content: string, files?: File[]) => void;
    disabled?: boolean;
  }) => (
    <div>
      <button disabled={disabled} onClick={() => onSendMessage('Follow-up question')}>
        Send stub message
      </button>
      <button
        disabled={disabled}
        onClick={() =>
          onSendMessage('Oversized file', [
            new File(['x'.repeat(4 * 1024 * 1024)], 'large.pdf', { type: 'application/pdf' }),
          ])
        }
      >
        Send oversized stub
      </button>
      <button
        disabled={disabled}
        onClick={() =>
          onSendMessage('Small file', [
            new File(['small'], 'small.pdf', { type: 'application/pdf' }),
          ])
        }
      >
        Send small file stub
      </button>
    </div>
  ),
}));

function renderPage(
  route = '/gp/query/1',
  state?: { draftMessage?: string },
) {
  seedAuth({ role: 'gp', username: 'Dr GP' });
  window.history.pushState(state ?? {}, '', route);
  return renderWithProviders(
    <Routes>
      <Route path="/gp/query/:queryId" element={<GPQueryDetailPage />} />
      <Route path="/gp/queries" element={<div>GP Queries</div>} />
      <Route path="/login" element={<div>Login</div>} />
    </Routes>,
    { routes: [{ pathname: route, state }] as never[] },
  );
}

describe('GPQueryDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    latestOnRefresh = null;
    latestOnFileContextTruncated = null;
    hookState.phase = 'idle';
    hookState.isStreaming = false;
    hookState.injectPlaceholder = false;
    hookState.injectStringTimestamp = false;
    hookState.stripGeneratingPlaceholders = false;
  });

  it('loads a consultation, edits metadata, sends a message, and shows submitted state', async () => {
    server.use(
      http.get('/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'submitted',
          severity: 'urgent',
        })),
      http.patch('/chats/:chatId', ({ params, request }) =>
        request.json().then((body) =>
          HttpResponse.json({
            ...mockChatWithMessages,
            id: Number(params.chatId),
            ...body,
            status: 'submitted',
            created_at: mockChatWithMessages.created_at,
            user_id: mockChatWithMessages.user_id,
            messages: mockChatWithMessages.messages,
          }),
        )),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/headache consultation/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/this consultation has been submitted for specialist review/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(mockStartPolling).toHaveBeenCalled();
    });

    await user.click(screen.getByRole('button', { name: /edit details/i }));
    const titleInput = screen.getByPlaceholderText(/consultation title/i);
    await user.clear(titleInput);
    await user.type(titleInput, 'Updated title');
    await user.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => {
      expect(screen.getByText(/updated title/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /send stub message/i }));

    await waitFor(() => {
      expect(mockConnectStream).toHaveBeenCalled();
    });
  }, 15000);

  it('shows not-found and send validation errors', async () => {
    server.use(http.get('/chats/:chatId', () => HttpResponse.json({ detail: 'Missing' }, { status: 404 })));
    renderPage('/gp/query/999');
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/consultation not found/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /back to consultations/i }));
    await waitFor(() => {
      expect(screen.getByText(/gp queries/i)).toBeInTheDocument();
    });
  });

  it('handles draft auto-send, file-size validation, and metadata save errors', async () => {
    server.use(
      http.get('/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'open',
          severity: 'high',
        })),
      http.patch('/chats/:chatId', () =>
        HttpResponse.json({ detail: 'Save failed' }, { status: 500 })),
      http.post('/chats/:chatId/files', () => new HttpResponse(null, { status: 204 })),
    );

    renderPage('/gp/query/1', { draftMessage: 'Draft from previous page' });
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/draft from previous page/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /edit details/i }));
    await user.click(screen.getByRole('button', { name: /^save$/i }));
    await waitFor(() => {
      expect(screen.getByText(/failed to update consultation details/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /cancel/i }));

    await user.click(screen.getByRole('button', { name: /send oversized stub/i }));
    await waitFor(() => {
      expect(screen.getByText(/maximum size is 3 mb/i)).toBeInTheDocument();
    });
  });

  it('shows reviewing banner from backend state', async () => {
    server.use(
      http.get('/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'assigned',
        })),
    );
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/currently reviewing this consultation/i)).toBeInTheDocument();
    });
  });

  it('shows approved banner from backend state', async () => {
    server.use(
      http.get('/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'approved',
        })),
    );
    renderPage();

    await waitFor(() => {
      expect(screen.getAllByText(/approved by a specialist/i).length).toBeGreaterThan(0);
    });
  });

  it('shows rejected banner from backend state', async () => {
    server.use(
      http.get('/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'rejected',
        })),
    );
    renderPage();

    await waitFor(() => {
      expect(screen.getAllByText(/rejected by a specialist/i).length).toBeGreaterThan(0);
    });
  });

  it('shows terminal-state fallback title and hides editing/input controls', async () => {
    server.use(
      http.get('/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          title: '',
          specialty: null,
          status: 'approved',
          severity: null,
          messages: [],
        })),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/untitled consultation/i)).toBeInTheDocument();
    });

    expect(screen.queryByRole('button', { name: /edit details/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /send stub message/i })).not.toBeInTheDocument();
  });

  it('surfaces send failures from the backend', async () => {
    server.use(
      http.get('/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'open',
        })),
      http.post('/chats/:chatId/message', () =>
        HttpResponse.json({ detail: 'Send failed' }, { status: 500 })),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/headache consultation/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /send stub message/i }));

    await waitFor(() => {
      expect(screen.getByText(/send failed/i)).toBeInTheDocument();
    });
  });

  it('uploads small files before sending and reconciles a streaming placeholder', async () => {
    hookState.injectPlaceholder = true;
    server.use(
      http.get('/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'open',
          messages: [
            ...mockChatWithMessages.messages,
            { id: 999, content: 'Persisted AI', sender: 'ai', created_at: '2025-01-15T10:02:00Z' },
          ],
        })),
      http.post('/chats/:chatId/files', () => HttpResponse.json({ id: 'f1' })),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/headache consultation/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /send small file stub/i }));

    await waitFor(() => {
      expect(mockConnectStream).toHaveBeenCalled();
    });
  });

  it('reconciles to fetched messages when no streaming placeholder remains', async () => {
    hookState.stripGeneratingPlaceholders = true;
    let getChatCalls = 0;

    server.use(
      http.get('/chats/:chatId', ({ params }) => {
        getChatCalls += 1;
        const base = { ...mockChatWithMessages, id: Number(params.chatId), status: 'open' };
        if (getChatCalls < 2) {
          return HttpResponse.json(base);
        }
        return HttpResponse.json({
          ...base,
          messages: [
            ...mockChatWithMessages.messages,
            { id: 777, content: 'Fetched AI response', sender: 'ai', created_at: '2025-01-15T10:03:00Z' },
          ],
        });
      }),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/headache consultation/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /send stub message/i }));

    await waitFor(() => {
      expect(screen.getByText('Fetched AI response')).toBeInTheDocument();
    });
  });

  it('keeps sending the message when one uploaded file fails and shows attached files', async () => {
    let uploadCount = 0;
    server.use(
      http.get('/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'open',
          files: [
            {
              id: 10,
              filename: 'existing.pdf',
              file_type: 'application/pdf',
              file_size: 1234,
              created_at: '2025-01-15T10:00:00Z',
            },
          ],
        })),
      http.post('/chats/:chatId/files', () => {
        uploadCount += 1;
        if (uploadCount === 1) {
          return HttpResponse.json({ detail: 'Upload failed' }, { status: 422 });
        }
        return HttpResponse.json({ id: 2, filename: 'ok.pdf' });
      }),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getAllByText(/existing\.pdf/i).length).toBeGreaterThan(0);
    });

    await user.click(screen.getByRole('button', { name: /send small file stub/i }));

    await waitFor(() => {
      expect(mockConnectStream).toHaveBeenCalled();
    });
  });

  it('shows generic upload failure text when upload rejects with non-Error reason', async () => {
    vi.spyOn(api, 'uploadChatFile').mockRejectedValueOnce('upload-problem');

    server.use(
      http.get('/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'open',
        })),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/headache consultation/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /send small file stub/i }));

    await waitFor(() => {
      expect(screen.getByText(/upload failed/i)).toBeInTheDocument();
    });
  });

  it('renders consultation files without size badges when file_size is missing', async () => {
    server.use(
      http.get('/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'open',
          files: [
            {
              id: 22,
              filename: 'no-size.pdf',
              file_type: 'application/pdf',
              file_size: null,
              created_at: '2025-01-15T10:00:00Z',
            },
          ],
        })),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getAllByText('no-size.pdf').length).toBeGreaterThan(0);
    });
    expect(screen.queryByText(/kb/i)).not.toBeInTheDocument();
  });

  it('refreshes through the stream hook callback and preserves a draft streaming placeholder', async () => {
    hookState.injectPlaceholder = true;
    server.use(
      http.get('/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'open',
          messages: [
            ...mockChatWithMessages.messages,
            { id: 999, content: 'Persisted AI', sender: 'ai', created_at: '2025-01-15T10:02:00Z' },
          ],
        })),
    );

    renderPage('/gp/query/1', { draftMessage: 'Draft from previous page' });

    await waitFor(() => {
      expect(screen.getByText(/draft from previous page/i)).toBeInTheDocument();
    });

    await waitFor(async () => {
      await latestOnRefresh?.();
      expect(screen.getByText(/persisted ai/i)).toBeInTheDocument();
    });
  });

  it('auto-connects when the latest message still needs an AI response', async () => {
    server.use(
      http.get('/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'open',
          messages: [
            { id: 1, content: 'Patient follow-up', sender: 'user', created_at: '2025-01-15T10:05:00Z' },
          ],
        })),
    );

    renderPage();

    await waitFor(() => {
      expect(mockConnectStream).toHaveBeenCalled();
    });
  });

  it('does not auto-connect when the stream is already in fallback polling', () => {
    expect(shouldAutoConnectGpStream({
      hasChat: true,
      streamConnected: false,
      sending: false,
      streamPhase: 'fallback_polling',
      hasPendingAIResponse: true,
      hasRevisionInProgress: false,
    })).toBe(false);
  });

  it('shows file truncation warning when onFileContextTruncated is called', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/headache consultation/i)).toBeInTheDocument();
    });

    act(() => {
      latestOnFileContextTruncated?.();
    });

    await waitFor(() => {
      expect(screen.getByText(/files were too long and were truncated/i)).toBeInTheDocument();
    });
  });

  it('does not auto-connect while a send is already in progress', () => {
    expect(shouldAutoConnectGpStream({
      hasChat: true,
      streamConnected: false,
      sending: true,
      streamPhase: 'idle',
      hasPendingAIResponse: true,
      hasRevisionInProgress: false,
    })).toBe(false);
  });

  it('shows draft send failure when the backend rejects the initial draft message', async () => {
    server.use(
      http.get('/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'open',
          severity: 'high',
        })),
      http.post('/chats/:chatId/message', () =>
        HttpResponse.json({ detail: 'Draft send failed' }, { status: 500 })),
    );

    renderPage('/gp/query/1', { draftMessage: 'Draft from previous page' });

    await waitFor(() => {
      expect(screen.getByText(/failed to send message/i)).toBeInTheDocument();
    });
  });

  it('handles non-Date timestamps injected during streaming without crashing', async () => {
    hookState.injectStringTimestamp = true;
    server.use(
      http.get('/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'open',
        })),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/headache consultation/i)).toBeInTheDocument();
    });

    // Send a message to trigger connectStream which injects the string-timestamp message
    await user.click(screen.getByRole('button', { name: /send stub message/i }));

    await waitFor(() => {
      expect(mockConnectStream).toHaveBeenCalled();
    });

    // Rendering remains stable even when streaming injects messages with non-Date timestamps.
    expect(screen.getByText(/headache consultation/i)).toBeInTheDocument();
  });

  it('clears specialty and severity metadata and navigates back from the loaded page', async () => {
    server.use(
      http.get('/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'open',
          specialty: 'neurology',
          severity: 'urgent',
        })),
      http.patch('/chats/:chatId', async ({ params, request }) => {
        const body = await request.json() as { specialty?: string; severity?: string };
        expect(body.specialty).toBeUndefined();
        expect(body.severity).toBeUndefined();
        return HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          title: 'Headache Consultation',
          status: 'open',
          specialty: null,
          severity: null,
          messages: mockChatWithMessages.messages,
        });
      }),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/headache consultation/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /edit details/i }));
    await user.clear(screen.getByPlaceholderText(/specialty/i));
    await user.selectOptions(screen.getByDisplayValue('Urgent'), '');
    await user.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => {
      expect(screen.queryByText(/^neurology$/i)).not.toBeInTheDocument();
    });

    await user.click(screen.getAllByRole('button', { name: /back to consultations/i })[0]);
    await waitFor(() => {
      expect(screen.getByText(/gp queries/i)).toBeInTheDocument();
    });
  });
});
