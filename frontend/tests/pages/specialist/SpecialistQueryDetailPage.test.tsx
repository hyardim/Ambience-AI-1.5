import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import {
  SpecialistQueryDetailPage,
} from '@/pages/specialist/SpecialistQueryDetailPage';
import {
  canAssignSpecialist,
  canSubmitManualResponse,
  canSubmitReviewAction,
  shouldAutoConnectSpecialistStream,
} from '@/utils/specialistQueryDetail';
import { renderWithProviders, seedAuth } from '@test/utils';
import { server } from '@test/mocks/server';
import { mockChatWithMessages, mockSpecialistUser } from '@test/mocks/handlers';
import type { Message } from '@/types';

const mockConnectStream = vi.fn(() => Promise.resolve());
const mockStartPolling = vi.fn();
const mockStopPolling = vi.fn();
let latestOnRefresh: (() => Promise<void>) | null = null;
let latestOnFileContextTruncated: (() => void) | null = null;
const hookState = {
  phase: 'idle' as 'idle' | 'connecting' | 'streaming' | 'completed' | 'fallback_polling',
  isStreaming: false,
  injectPlaceholder: false,
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
  }: {
    onSendMessage: (content: string, files?: File[]) => void;
  }) => (
    <div>
      <button onClick={() => onSendMessage('Specialist note')}>Send specialist note</button>
      <button
        onClick={() =>
          onSendMessage('Specialist small file', [new File(['small'], 'note.txt', { type: 'text/plain' })])
        }
      >
        Send specialist small file
      </button>
      <button
        onClick={() =>
          onSendMessage('Specialist file', [new File(['x'.repeat(4 * 1024 * 1024)], 'too-large.pdf', { type: 'application/pdf' })])
        }
      >
        Send specialist oversized
      </button>
    </div>
  ),
}));

vi.mock('@/components/ChatMessage', () => ({
  ChatMessage: ({
    message,
    onApprove,
    onApproveWithComment,
    onRequestChanges,
    onManualResponse,
    onEditResponse,
  }: {
    message: { content: string };
    onApprove?: () => void;
    onApproveWithComment?: () => void;
    onRequestChanges?: () => void;
    onManualResponse?: () => void;
    onEditResponse?: () => void;
  }) => (
    <div>
      <div>{message.content}</div>
      {onApprove ? <button onClick={onApprove}>Approve action</button> : null}
      {onApproveWithComment ? <button onClick={onApproveWithComment}>Approve with comment action</button> : null}
      {onRequestChanges ? <button onClick={onRequestChanges}>Request changes action</button> : null}
      {onManualResponse ? <button onClick={onManualResponse}>Manual response action</button> : null}
      {onEditResponse ? <button onClick={onEditResponse}>Edit response action</button> : null}
    </div>
  ),
}));

function renderPage(route = '/specialist/query/1') {
  seedAuth({ role: 'specialist', username: 'Dr Specialist' });
  return renderWithProviders(
    <Routes>
      <Route path="/specialist/query/:queryId" element={<SpecialistQueryDetailPage />} />
      <Route path="/specialist/queries" element={<div>Specialist Queries</div>} />
      <Route path="/login" element={<div>Login</div>} />
    </Routes>,
    { routes: [route] },
  );
}

describe('SpecialistQueryDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    latestOnRefresh = null;
    latestOnFileContextTruncated = null;
    hookState.phase = 'idle';
    hookState.isStreaming = false;
    hookState.injectPlaceholder = false;
  });

  it('loads a submitted chat and allows assignment', async () => {
    server.use(
      http.get('/auth/me', () => HttpResponse.json(mockSpecialistUser)),
      http.get('/specialist/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'submitted',
        })),
      http.post('/specialist/chats/:chatId/assign', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'assigned',
          specialist_id: mockSpecialistUser.id,
        })),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/headache consultation/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /assign to me/i }));
    await waitFor(() => {
      expect(screen.getByText(/review actions are available on each ai response below/i)).toBeInTheDocument();
    });
  });

  it('handles approve, approve with comment, request changes, and manual response flows', async () => {
    server.use(
      http.get('/auth/me', () => HttpResponse.json(mockSpecialistUser)),
      http.get('/specialist/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'reviewing',
          messages: [
            {
              id: 2,
              content: 'AI answer',
              sender: 'ai',
              created_at: '2025-01-15T10:01:05Z',
            },
          ],
        })),
      http.post('/specialist/chats/:chatId/message', () =>
        HttpResponse.json({ status: 'ok', message_id: 99 })),
      http.post('/specialist/chats/:chatId/messages/:messageId/review', () =>
        HttpResponse.json({ ...mockChatWithMessages, status: 'reviewing' })),
      http.post('/chats/:chatId/files', () => HttpResponse.json({ id: 'file-1', name: 'source.txt', size: '1KB', type: 'txt' })),
    );

    renderPage();
    const user = userEvent.setup({ applyAccept: false });

    await waitFor(() => {
      expect(screen.getByText(/ai answer/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /approve action/i }));
    await user.click(screen.getByRole('button', { name: /confirm approval/i }));

    await user.click(screen.getByRole('button', { name: /approve with comment action/i }));
    await user.type(screen.getByPlaceholderText(/add your comment for the gp/i), 'Looks good');
    await user.click(screen.getByRole('button', { name: /send & approve/i }));

    await user.click(screen.getByRole('button', { name: /request changes action/i }));
    await user.type(screen.getByPlaceholderText(/describe the required changes/i), 'Clarify dosing');
    await user.click(screen.getByRole('button', { name: /submit feedback/i }));
    expect(mockConnectStream).toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: /manual response action/i }));
    await user.type(screen.getByPlaceholderText(/type your replacement response/i), 'Use this instead');
    await user.type(screen.getByPlaceholderText(/e\.g\. nice ng228, bsr guideline 2023/i), 'NICE CG1');
    const fileInput = screen.getByText(/attach files/i).parentElement?.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(fileInput, new File(['hello'], 'source.txt', { type: 'text/plain' }));
    await user.click(screen.getByRole('button', { name: /send manual response/i }));
  }, 15000);

  it('shows close-and-approve flow, send errors, oversize validation, and not-found state', async () => {
    server.use(
      http.get('/auth/me', () => HttpResponse.json(mockSpecialistUser)),
      http.get('/specialist/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'reviewing',
          messages: [
            {
              id: 2,
              content: 'Reviewed AI answer',
              sender: 'ai',
              created_at: '2025-01-15T10:01:05Z',
              review_status: 'approved',
            },
          ],
        })),
      http.post('/specialist/chats/:chatId/review', () =>
        HttpResponse.json({ ...mockChatWithMessages, status: 'approved' })),
      http.post('/specialist/chats/:chatId/message', () =>
        HttpResponse.json({ detail: 'Send failed' }, { status: 500 })),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/all ai responses have been reviewed/i)).toBeInTheDocument();
    });

    await user.click(screen.getAllByRole('button', { name: /close & approve consultation/i })[0]);
    await user.click(screen.getByRole('button', { name: /confirm close & approve/i }));

    await user.click(screen.getByRole('button', { name: /send specialist note/i }));
    await waitFor(() => {
      expect(screen.getByText(/send failed/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /send specialist oversized/i }));
    await waitFor(() => {
      expect(screen.getByText(/maximum size is 3 mb/i)).toBeInTheDocument();
    });

    server.use(http.get('/specialist/chats/:chatId', () => HttpResponse.json({ detail: 'Missing' }, { status: 404 })));
    renderPage('/specialist/query/999');
    await waitFor(() => {
      expect(screen.getByText(/query not found/i)).toBeInTheDocument();
    });
  });

  it('resets modal state on cancel and shows terminal consultation banner', async () => {
    server.use(
      http.get('/auth/me', () => HttpResponse.json(mockSpecialistUser)),
      http.get('/specialist/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          title: '',
          specialty: null,
          status: 'rejected',
          messages: [
            {
              id: 2,
              content: 'AI answer',
              sender: 'ai',
              created_at: '2025-01-15T10:01:05Z',
              review_status: 'rejected',
            },
          ],
        })),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/untitled consultation/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/consultation rejected/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /send specialist note/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /approve with comment action/i }));
    await user.type(screen.getByPlaceholderText(/add your comment for the gp/i), 'Temporary');
    await user.click(screen.getByRole('button', { name: /^cancel$/i }));
    expect(screen.queryByDisplayValue('Temporary')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /request changes action/i }));
    await user.type(screen.getByPlaceholderText(/describe the required changes/i), 'Need details');
    await user.click(screen.getByRole('button', { name: /^cancel$/i }));
    expect(screen.queryByDisplayValue('Need details')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /manual response action/i }));
    await user.type(screen.getByPlaceholderText(/type your replacement response/i), 'Replacement');
    await user.click(screen.getByRole('button', { name: /^cancel$/i }));
    expect(screen.queryByDisplayValue('Replacement')).not.toBeInTheDocument();
  });

  it('shows manual response file-size validation without submitting', async () => {
    server.use(
      http.get('/auth/me', () => HttpResponse.json(mockSpecialistUser)),
      http.get('/specialist/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'reviewing',
          messages: [
            {
              id: 2,
              content: 'AI answer',
              sender: 'ai',
              created_at: '2025-01-15T10:01:05Z',
            },
          ],
        })),
    );

    renderPage();
    const user = userEvent.setup({ applyAccept: false });

    await waitFor(() => {
      expect(screen.getByText(/ai answer/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /manual response action/i }));
    await user.type(screen.getByPlaceholderText(/type your replacement response/i), 'Use this instead');
    const fileInput = screen.getByText(/attach files/i).parentElement?.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(
      fileInput,
      new File(['x'.repeat(4 * 1024 * 1024)], 'too-large.pdf', { type: 'application/pdf' }),
    );
    await user.click(screen.getByRole('button', { name: /send manual response/i }));

    await waitFor(() => {
      expect(screen.getByText(/maximum size is 3 mb/i)).toBeInTheDocument();
    });
  });

  it('auto-connects when a pending GP message is waiting for AI generation', async () => {
    server.use(
      http.get('/auth/me', () => HttpResponse.json(mockSpecialistUser)),
      http.get('/specialist/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'reviewing',
          messages: [
            {
              id: 2,
              content: 'Can you refine this?',
              sender: 'user',
              created_at: '2025-01-15T10:01:05Z',
            },
          ],
        })),
    );

    renderPage();

    await waitFor(() => {
      expect(mockConnectStream).toHaveBeenCalled();
    });
  });

  it('exposes specialist action guard helpers', () => {
    expect(canAssignSpecialist(1)).toBe(true);
    expect(canAssignSpecialist(null)).toBe(false);
    expect(canSubmitReviewAction('Looks good', 2)).toBe(true);
    expect(canSubmitReviewAction('   ', 2)).toBe(false);
    expect(canSubmitReviewAction('Looks good', null)).toBe(false);
    expect(canSubmitManualResponse('Answer', 2)).toBe(true);
    expect(canSubmitManualResponse('   ', 2)).toBe(false);
    expect(canSubmitManualResponse('Answer', null)).toBe(false);
  });

  it('only auto-connects for eligible specialist stream states', () => {
    expect(shouldAutoConnectSpecialistStream({
      hasChat: true,
      streamConnected: false,
      streamPhase: 'idle',
      hasPendingAIResponse: true,
      hasRevisionInProgress: false,
    })).toBe(true);
    expect(shouldAutoConnectSpecialistStream({
      hasChat: true,
      streamConnected: false,
      streamPhase: 'fallback_polling',
      hasPendingAIResponse: false,
      hasRevisionInProgress: true,
    })).toBe(true);
    expect(shouldAutoConnectSpecialistStream({
      hasChat: true,
      streamConnected: false,
      streamPhase: 'streaming',
      hasPendingAIResponse: true,
      hasRevisionInProgress: false,
    })).toBe(false);
    expect(shouldAutoConnectSpecialistStream({
      hasChat: false,
      streamConnected: false,
      streamPhase: 'idle',
      hasPendingAIResponse: true,
      hasRevisionInProgress: false,
    })).toBe(false);
  });

  it('refreshes through the stream hook callback and uploads a small specialist file successfully', async () => {
    server.use(
      http.get('/auth/me', () => HttpResponse.json(mockSpecialistUser)),
      http.get('/specialist/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'reviewing',
          messages: [
            {
              id: 2,
              content: 'AI answer',
              sender: 'ai',
              created_at: '2025-01-15T10:01:05Z',
            },
          ],
        })),
      http.post('/chats/:chatId/files', () => HttpResponse.json({ id: 'small-file' })),
      http.post('/specialist/chats/:chatId/message', () =>
        HttpResponse.json({ status: 'ok', message_id: 199 })),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/ai answer/i)).toBeInTheDocument();
    });

    await act(async () => {
      await latestOnRefresh?.();
    });
    await user.click(screen.getByRole('button', { name: /send specialist small file/i }));
  });

  it('still sends specialist messages when one uploaded file fails', async () => {
    server.use(
      http.get('/auth/me', () => HttpResponse.json(mockSpecialistUser)),
      http.get('/specialist/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'reviewing',
          messages: [
            {
              id: 2,
              content: 'AI answer',
              sender: 'ai',
              created_at: '2025-01-15T10:01:05Z',
            },
          ],
        })),
      http.post('/chats/:chatId/files', () =>
        HttpResponse.json({ detail: 'Upload failed' }, { status: 500 })),
      http.post('/specialist/chats/:chatId/message', () =>
        HttpResponse.json({ status: 'ok', message_id: 199 })),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/ai answer/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /send specialist small file/i }));

    await waitFor(() => {
      expect(screen.getByText(/message sent, but some files failed to upload/i)).toBeInTheDocument();
    });
  });

  it('renders empty consultations, supports canceling confirmation modals, and navigates back from not-found state', async () => {
    server.use(
      http.get('/auth/me', () => HttpResponse.json(mockSpecialistUser)),
      http.get('/specialist/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          title: 'Ready to close',
          status: 'reviewing',
          messages: [
            {
              id: 2,
              content: 'Reviewed AI answer',
              sender: 'ai',
              created_at: '2025-01-15T10:01:05Z',
              review_status: 'approved',
            },
          ],
        })),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/all ai responses have been reviewed/i)).toBeInTheDocument();
    });

    await user.click(screen.getAllByRole('button', { name: /close & approve consultation/i })[0]);
    await user.click(screen.getByRole('button', { name: /^cancel$/i }));
    expect(screen.getAllByText(/close & approve consultation/i).length).toBeGreaterThan(0);

    server.use(
      http.get('/specialist/chats/:chatId', () => HttpResponse.json({ detail: 'Missing' }, { status: 404 })),
    );
    renderPage('/specialist/query/999');

    await waitFor(() => {
      expect(screen.getByText(/query not found/i)).toBeInTheDocument();
    });

    await user.click(screen.getAllByRole('button', { name: /back to queries/i })[1]);
    await waitFor(() => {
      expect(screen.getByText(/specialist queries/i)).toBeInTheDocument();
    });
  });

  it('surfaces approval, review, and manual response errors', async () => {
    server.use(
      http.get('/auth/me', () => HttpResponse.json(mockSpecialistUser)),
      http.get('/specialist/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'reviewing',
          messages: [
            {
              id: 2,
              content: 'AI answer',
              sender: 'ai',
              created_at: '2025-01-15T10:01:05Z',
            },
          ],
        })),
      http.post('/specialist/chats/:chatId/messages/:messageId/review', ({ request }) =>
        request.json().then((body) => {
          const action = (body as { action?: string }).action;
          const detail =
            action === 'approve'
              ? 'Approve failed'
              : action === 'request_changes'
                ? 'Request failed'
                : 'Manual failed';
          return HttpResponse.json({ detail }, { status: 500 });
        })),
      http.post('/specialist/chats/:chatId/message', () =>
        HttpResponse.json({ detail: 'Comment failed' }, { status: 500 })),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/ai answer/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /approve action/i }));
    await user.click(screen.getByRole('button', { name: /confirm approval/i }));
    await waitFor(() => {
      expect(screen.getByText(/approve failed/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /approve action/i }));
    await user.click(screen.getByRole('button', { name: /^cancel$/i }));

    await user.click(screen.getByRole('button', { name: /approve with comment action/i }));
    await user.type(screen.getByPlaceholderText(/add your comment for the gp/i), 'Needs context');
    await user.click(screen.getByRole('button', { name: /send & approve/i }));
    await waitFor(() => {
      expect(screen.getByText(/comment failed/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /request changes action/i }));
    await user.type(screen.getByPlaceholderText(/describe the required changes/i), 'Please revise');
    await user.click(screen.getByRole('button', { name: /submit feedback/i }));
    await waitFor(() => {
      expect(screen.getByText(/request failed/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /manual response action/i }));
    await user.type(screen.getByPlaceholderText(/type your replacement response/i), 'Replacement');
    await user.click(screen.getByRole('button', { name: /send manual response/i }));
    await waitFor(() => {
      expect(screen.getByText(/manual failed/i)).toBeInTheDocument();
    });
  }, 15000);

  it('shows assign failure when submitting a new consultation assignment', async () => {
    server.use(
      http.get('/auth/me', () => HttpResponse.json(mockSpecialistUser)),
      http.get('/specialist/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'submitted',
        })),
      http.post('/specialist/chats/:chatId/assign', () =>
        HttpResponse.json({ detail: 'Assign failed' }, { status: 500 })),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /assign to me/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /assign to me/i }));
    await waitFor(() => {
      expect(screen.getByText(/assign failed/i)).toBeInTheDocument();
    });
  });

  it('surfaces close-and-approve failures from either close action', async () => {
    server.use(
      http.get('/auth/me', () => HttpResponse.json(mockSpecialistUser)),
      http.get('/specialist/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'reviewing',
          messages: [
            {
              id: 2,
              content: 'Reviewed AI answer',
              sender: 'ai',
              created_at: '2025-01-15T10:01:05Z',
              review_status: 'approved',
            },
          ],
        })),
      http.post('/specialist/chats/:chatId/review', () =>
        HttpResponse.json({ detail: 'Close failed' }, { status: 500 })),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: /close & approve consultation/i }).length).toBeGreaterThan(1);
    });

    await user.click(screen.getAllByRole('button', { name: /close & approve consultation/i })[1]);
    await user.click(screen.getByRole('button', { name: /confirm close & approve/i }));
    await waitFor(() => {
      expect(screen.getByText(/close failed/i)).toBeInTheDocument();
    });
  });

  it('shows file truncation warning when onFileContextTruncated is called', async () => {
    server.use(
      http.get('/auth/me', () => HttpResponse.json(mockSpecialistUser)),
      http.get('/specialist/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'reviewing',
          messages: [],
        })),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/headache consultation/i)).toBeInTheDocument();
    });

    act(() => {
      latestOnFileContextTruncated?.();
    });

    await waitFor(() => {
      expect(screen.getByText(/file context was truncated/i)).toBeInTheDocument();
    });
  });

  it('handles edit response flow with sources and feedback', async () => {
    server.use(
      http.get('/auth/me', () => HttpResponse.json(mockSpecialistUser)),
      http.get('/specialist/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'reviewing',
          messages: [
            {
              id: 2,
              content: 'AI answer to edit',
              sender: 'ai',
              created_at: '2025-01-15T10:01:05Z',
            },
          ],
        })),
      http.post('/specialist/chats/:chatId/messages/:messageId/review', () =>
        HttpResponse.json({ ...mockChatWithMessages, status: 'reviewing' })),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/ai answer to edit/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /edit response action/i }));

    // The modal should be pre-filled with the current content
    await waitFor(() => {
      expect(screen.getByDisplayValue('AI answer to edit')).toBeInTheDocument();
    });

    // Clear existing text and type new content
    const contentTextarea = screen.getByDisplayValue('AI answer to edit');
    await user.clear(contentTextarea);
    await user.type(contentTextarea, 'Edited answer');

    await user.type(screen.getByPlaceholderText(/optional. add one source per line/i), 'NICE CG1');
    await user.type(screen.getByPlaceholderText(/optional. explain what you changed/i), 'Fixed phrasing');
    await user.click(screen.getByRole('button', { name: /save edited response/i }));
  }, 15000);

  it('surfaces edit response errors', async () => {
    server.use(
      http.get('/auth/me', () => HttpResponse.json(mockSpecialistUser)),
      http.get('/specialist/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'reviewing',
          messages: [
            {
              id: 2,
              content: 'AI answer',
              sender: 'ai',
              created_at: '2025-01-15T10:01:05Z',
            },
          ],
        })),
      http.post('/specialist/chats/:chatId/messages/:messageId/review', () =>
        HttpResponse.json({ detail: 'Edit failed' }, { status: 500 })),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/ai answer/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /edit response action/i }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save edited response/i })).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /save edited response/i }));

    await waitFor(() => {
      expect(screen.getByText(/edit failed/i)).toBeInTheDocument();
    });
  });

  it('resets edit response modal state on cancel', async () => {
    server.use(
      http.get('/auth/me', () => HttpResponse.json(mockSpecialistUser)),
      http.get('/specialist/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'reviewing',
          messages: [
            {
              id: 2,
              content: 'AI answer',
              sender: 'ai',
              created_at: '2025-01-15T10:01:05Z',
            },
          ],
        })),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/ai answer/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /edit response action/i }));
    await waitFor(() => {
      expect(screen.getByDisplayValue('AI answer')).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /^cancel$/i }));
    expect(screen.queryByDisplayValue('AI answer')).not.toBeInTheDocument();
  });

  it('navigates back from the loaded detail header button', async () => {
    server.use(
      http.get('/auth/me', () => HttpResponse.json(mockSpecialistUser)),
      http.get('/specialist/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'reviewing',
          messages: [],
        })),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/headache consultation/i)).toBeInTheDocument();
    });

    await user.click(screen.getAllByRole('button', { name: /back to queries/i })[0]);
    await waitFor(() => {
      expect(screen.getByText(/specialist queries/i)).toBeInTheDocument();
    });
  });
});
