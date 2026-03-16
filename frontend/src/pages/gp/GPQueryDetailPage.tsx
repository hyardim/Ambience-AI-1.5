import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { ArrowLeft, Loader2, ClipboardCheck } from 'lucide-react';
import { Header } from '../../components/Header';
import { ChatMessage } from '../../components/ChatMessage';
import { ChatInput } from '../../components/ChatInput';
import { useAuth } from '../../contexts/useAuth';
import { StatusBadge, SeverityBadge } from '../../components/Badges';
import { useChatStream } from '../../hooks/useChatStream';
import { toFrontendMessage } from '../../utils/messageMapping';
import {
  getChat,
  sendMessage as apiSendMessage,
  updateChat as apiUpdateChat,
  uploadChatFile,
} from '../../services/api';
import type { BackendChatWithMessages, ChatUpdateRequest } from '../../types/api';
import type { Message } from '../../types';
import { getErrorMessage } from '../../utils/errors';
import { orFallback } from '../../utils/value';

export function GPQueryDetailPage() {
  const { queryId } = useParams<{ queryId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const { username, logout } = useAuth();
  const [chat, setChat] = useState<BackendChatWithMessages | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [editingMeta, setEditingMeta] = useState(false);
  const [savingMeta, setSavingMeta] = useState(false);
  const [editMeta, setEditMeta] = useState<ChatUpdateRequest>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);
  // Guard: auto-send the draft message from GPNewQueryPage only once
  const draftSentRef = useRef(false);

  // ── Streaming state machine ────────────────────────────────────────────
  const refreshChat = useCallback(async () => {
    /* v8 ignore next */
    /* v8 ignore next */
    if (!queryId) return;
    try {
      const found = await getChat(Number(queryId));
      setChat(found);
      setMessages(found.messages.map(m => toFrontendMessage(m, orFallback(username, 'GP User'))));
    /* v8 ignore next */
    } catch { /* silent refresh */ }
  }, [queryId, username]);

  const { phase: streamPhase, isStreaming: streamConnected, connectStream, startPolling, stopPolling } = useChatStream(
    setMessages,
    { chatId: chat?.id ?? null, onRefresh: refreshChat },
  );

  // ── Auto-send draft message passed from GPNewQueryPage ───────────────
  const draftMessage = (location.state as { draftMessage?: string } | null)?.draftMessage;

  const hasPendingAIResponse =
    messages.length > 0 && messages[messages.length - 1].senderType === 'gp';

  // Also poll when the latest AI message is still generating (revision in progress)
  const hasRevisionInProgress =
    messages.length > 0 &&
    messages[messages.length - 1].senderType === 'ai' &&
    messages[messages.length - 1].isGenerating === true;

  // Poll when the chat is in a review workflow and the status may change
  const chatStatus = chat?.status ?? '';
  const isInReview = ['submitted', 'assigned', 'reviewing'].includes(chatStatus);

  // Don't poll while actively sending: the backend hasn't persisted the message
  // yet, so a silent fetch would return an empty message list and clobber the
  // optimistic message that's already visible.
  const shouldPoll = (hasPendingAIResponse || hasRevisionInProgress || isInReview) && !streamConnected && !sending;

  // Delegate polling to the hook — start/stop based on derived shouldPoll flag
  useEffect(() => {
    /* v8 ignore next */
    if (!queryId) return;
    if (shouldPoll) {
      startPolling();
    } else {
      stopPolling();
    }
  }, [queryId, shouldPoll, startPolling, stopPolling]);

  const fetchChat = useCallback(async () => {
    /* v8 ignore next */
    if (!queryId) return;
    setLoading(true);
    setError('');
    try {
      const found = await getChat(Number(queryId));
      setChat(found);
      const mapped = found.messages.map(m => toFrontendMessage(m, orFallback(username, 'GP User')));
      // When a draft message is about to be sent, pre-populate the optimistic
      // user message in the same batch as loading=false so there's no
      // empty-messages flash between fetchChat completing and the draft effect.
      if (draftMessage && !draftSentRef.current) {
        setMessages([...mapped, {
          id: 'temp-draft',
          senderId: 'user',
          senderName: orFallback(username, 'GP User'),
          senderType: 'gp' as const,
          content: draftMessage,
          timestamp: new Date(),
        }]);
      } else {
        setMessages(mapped);
      }
    } catch {
      setChat(null);
      setError('Failed to load consultation');
    } finally {
      setLoading(false);
    }
  }, [draftMessage, queryId, username]);

  useEffect(() => {
    void fetchChat();
  }, [fetchChat]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  useEffect(() => {
    if (!chat || !draftMessage || draftSentRef.current) return;
    draftSentRef.current = true;

    navigate(location.pathname, { replace: true, state: {} });
    setSending(true);

    void (async () => {
      try {
        await connectStream(chat.id);
        await apiSendMessage(chat.id, draftMessage);
        const refreshed = await getChat(chat.id);
        setChat(refreshed);
        setMessages((prev) => {
          const streamingMsg = prev.find((m) => m.isGenerating && m.senderType === 'ai');
          const fetched = refreshed.messages.map((m) =>
            toFrontendMessage(m, orFallback(username, 'GP User')),
          );
          if (!streamingMsg) {
            return fetched;
          }
          return fetched.map((m) => (m.id === streamingMsg.id ? streamingMsg : m));
        });
      } catch {
        setError('Failed to send message');
      } finally {
        setSending(false);
      }
    })();
  }, [chat, connectStream, draftMessage, location.pathname, navigate, username]);

  // Auto-connect SSE when there's pending AI work and no active stream
  useEffect(() => {
    /* v8 ignore next */
    if (!chat) return;
    if (streamConnected || sending) return;
    // Only auto-connect from idle. When fallback polling is active, avoid
    // tight reconnect loops against /stream under poor network conditions.
    /* v8 ignore next */
    if (streamPhase !== 'idle') return;
    if (!(hasPendingAIResponse || hasRevisionInProgress)) return;

    void connectStream(chat.id);
  }, [
    chat,
    connectStream,
    hasPendingAIResponse,
    hasRevisionInProgress,
    sending,
    streamConnected,
    streamPhase,
  ]);

  const handleSendMessage = async (content: string, files?: File[]) => {
    /* v8 ignore next */
    if (!chat || sending) return;
    setSending(true);

    // Optimistically add user message
    const userMsg: Message = {
      id: `temp-${Date.now()}`,
      senderId: 'user',
      senderName: orFallback(username, 'GP User'),
      senderType: 'gp',
      content,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMsg]);

    const MAX_FILE_SIZE = 3 * 1024 * 1024; // 3 MB
    try {
      // Upload any attached files before sending the message
      if (files && files.length > 0) {
        const oversized = files.filter(f => f.size > MAX_FILE_SIZE);
        if (oversized.length > 0) {
          setError(`File(s) too large: ${oversized.map(f => f.name).join(', ')}. Maximum size is 3 MB.`);
          setSending(false);
          return;
        }
        await Promise.all(files.map(f => uploadChatFile(chat.id, f)));
      }

      // Open SSE stream *once* before sending so we catch the AI generation events
      await connectStream(chat.id);

      await apiSendMessage(chat.id, content);
      // Also do one fetch to reconcile the user message id
      const refreshed = await getChat(chat.id);
      setChat(refreshed);

      // Merge: keep streaming placeholder if present, else use fetched messages
      setMessages((prev) => {
        const streamingMsg = prev.find((m) => m.isGenerating && m.senderType === 'ai');
        const fetched = refreshed.messages.map((m) =>
          toFrontendMessage(m, orFallback(username, 'GP User')),
        );
        if (streamingMsg) {
          // Replace the generating message from the fetch with our streaming version
          return fetched.map((m) =>
            m.id === streamingMsg.id ? streamingMsg : m,
          );
        }
        return fetched;
      });
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to send message'));
    } finally {
      setSending(false);
    }
  };

  const openMetaEditor = () => {
    /* v8 ignore next */
    if (!chat) return;
    setEditMeta({
      title: chat.title,
      specialty: chat.specialty,
      severity: chat.severity,
    });
    setEditingMeta(true);
  };

  const saveMeta = async () => {
    /* v8 ignore next */
    if (!chat) return;
    setSavingMeta(true);
    setError('');
    try {
      const updated = await apiUpdateChat(chat.id, {
        title: editMeta.title,
        specialty: editMeta.specialty || undefined,
        severity: editMeta.severity || undefined,
      });
      setChat({ ...chat, ...updated });
      setEditingMeta(false);
    } catch {
      setError('Failed to update consultation details');
    } finally {
      setSavingMeta(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
        <Header userRole="gp" userName={orFallback(username, 'GP User')} onLogout={logout} />
        <main className="flex-1 flex items-center justify-center">
          <Loader2 className="w-8 h-8 text-[#005eb8] animate-spin" />
        </main>
      </div>
    );
  }

  if (!chat) {
    return (
      <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
        <Header userRole="gp" userName={orFallback(username, 'GP User')} onLogout={logout} />
        <main className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <h1 className="text-2xl font-bold text-gray-900 mb-4">Consultation not found</h1>
            <button
              onClick={() => navigate('/gp/queries')}
              className="text-[#005eb8] hover:text-[#003087] font-medium"
            >
              Back to Consultations
            </button>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
      <Header userRole="gp" userName={orFallback(username, 'GP User')} onLogout={logout} />

      <main className="flex-1 max-w-5xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8 flex flex-col">
        {/* Back Button */}
        <button
          onClick={() => navigate('/gp/queries')}
          className="inline-flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-6"
        >
          <ArrowLeft className="w-5 h-5" />
          Back to Consultations
        </button>

        <div className="bg-white rounded-xl shadow-sm flex-1 flex flex-col overflow-hidden">
          {/* Chat Header */}
          <div className="p-6 border-b border-gray-200">
            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
              <div className="flex-1">
                <h1 className="text-xl font-bold text-gray-900 mb-2">{chat.title || 'Untitled Consultation'}</h1>
                <div className="flex flex-wrap items-center gap-3 text-sm text-gray-600">
                  <span className="font-medium">{orFallback(username, 'GP User')}</span>
                  <span>•</span>
                  <span>{new Date(chat.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}</span>
                  {chat.specialty && (
                    <>
                      <span>•</span>
                      <span className="capitalize">{chat.specialty}</span>
                    </>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {chat.severity && <SeverityBadge severity={chat.severity} />}
                <StatusBadge status={chat.status} />
                {!editingMeta && (chat.status === 'open' || chat.status === 'submitted') && (
                  <button
                    onClick={openMetaEditor}
                    className="px-3 py-1.5 text-xs font-medium text-[#005eb8] border border-[#005eb8] rounded-lg hover:bg-[#005eb8] hover:text-white transition-colors"
                  >
                    Edit details
                  </button>
                )}
              </div>
            </div>

            {editingMeta && (
              <div className="mt-4 p-4 border border-gray-200 rounded-lg bg-gray-50">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <input
                    type="text"
                    value={editMeta.title || ''}
                    onChange={(e) => setEditMeta(prev => ({ ...prev, title: e.target.value }))}
                    className="px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent"
                    placeholder="Consultation title"
                  />
                  <input
                    type="text"
                    value={editMeta.specialty || ''}
                    onChange={(e) => setEditMeta(prev => ({ ...prev, specialty: e.target.value || null }))}
                    className="px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent"
                    placeholder="Specialty"
                  />
                  <select
                    value={editMeta.severity || ''}
                    onChange={(e) => setEditMeta(prev => ({ ...prev, severity: e.target.value || null }))}
                    className="px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent bg-white"
                  >
                    <option value="">No severity</option>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="urgent">Urgent</option>
                  </select>
                </div>
                <div className="flex items-center justify-end gap-2 mt-3">
                  <button
                    onClick={() => setEditingMeta(false)}
                    className="px-3 py-1.5 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-100 text-sm"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={saveMeta}
                    disabled={savingMeta}
                    className="px-3 py-1.5 bg-[#005eb8] text-white rounded-lg hover:bg-[#003087] disabled:opacity-50 text-sm"
                  >
                    {savingMeta ? 'Saving…' : 'Save'}
                  </button>
                </div>
              </div>
            )}

            {/* Specialist review status banner */}
            {chat.status === 'submitted' && (
              <div className="mt-4 flex items-center gap-2 bg-amber-50 text-amber-800 px-4 py-3 rounded-lg border border-amber-200">
                <ClipboardCheck className="w-5 h-5 shrink-0" />
                <p className="text-sm">This consultation has been submitted for specialist review. You will be notified once a specialist responds.</p>
              </div>
            )}
            {(chat.status === 'assigned' || chat.status === 'reviewing') && (
              <div className="mt-4 flex items-center gap-2 bg-blue-50 text-blue-800 px-4 py-3 rounded-lg border border-blue-200">
                <ClipboardCheck className="w-5 h-5 shrink-0" />
                <p className="text-sm">A specialist is currently reviewing this consultation. Individual AI response statuses are shown on each message below.</p>
              </div>
            )}
            {chat.status === 'approved' && (
              <div className="mt-4 flex items-center gap-2 bg-green-50 text-green-800 px-4 py-3 rounded-lg border border-green-200">
                <ClipboardCheck className="w-5 h-5 shrink-0" />
                <p className="text-sm">This consultation has been approved by a specialist. Approved AI responses are marked below.</p>
              </div>
            )}
            {chat.status === 'rejected' && (
              <div className="mt-4 flex items-center gap-2 bg-red-50 text-red-800 px-4 py-3 rounded-lg border border-red-200">
                <ClipboardCheck className="w-5 h-5 shrink-0" />
                <p className="text-sm">This consultation has been rejected by a specialist. See the messages below for details.</p>
              </div>
            )}
          </div>

          {/* Error */}
          {error && (
            <div className="mx-6 mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
              {error}
            </div>
          )}

          {/* Chat Messages */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {messages.map(message => {
              const inReviewWorkflow = ['submitted', 'assigned', 'reviewing', 'approved', 'rejected'].includes(chat.status);
              return (
                <ChatMessage
                  key={message.id}
                  message={message}
                  isOwnMessage={message.senderType === 'gp'}
                  showReviewStatus={inReviewWorkflow}
                />
              );
            })}
            {hasPendingAIResponse && !streamConnected && (
              <div className="flex gap-4">
                <div className="shrink-0">
                  <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-blue-100 flex items-center justify-center">
                    <Loader2 className="w-5 h-5 text-[#005eb8] animate-spin" />
                  </div>
                </div>
                <div className="flex-1 max-w-3xl">
                  <div className="font-semibold text-gray-900 text-sm sm:text-base mb-2">NHS AI Assistant</div>
                  <div className="rounded-2xl px-4 sm:px-5 py-3 sm:py-4 bg-white border-l-4 border-[#005eb8] shadow-sm">
                    <div className="flex items-center gap-1.5 py-1">
                      <span className="w-2 h-2 rounded-full bg-[#005eb8] animate-bounce [animation-delay:-0.3s]"></span>
                      <span className="w-2 h-2 rounded-full bg-[#005eb8] animate-bounce [animation-delay:-0.15s]"></span>
                      <span className="w-2 h-2 rounded-full bg-[#005eb8] animate-bounce"></span>
                    </div>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Chat Input — only available before specialist picks up the chat */}
          {(chat.status === 'open' || chat.status === 'submitted') && (
            <div className="border-t border-gray-200 p-4">
              <ChatInput onSendMessage={handleSendMessage} disabled={sending} />
            </div>
          )}

          {/* Closed banner — bottom */}
          {chat.status === 'approved' && (
            <div className="border-t border-green-200 bg-green-50 px-6 py-3 flex items-center gap-2 text-green-800">
              <ClipboardCheck className="w-4 h-4 shrink-0" />
              <p className="text-sm">This consultation has been approved by a specialist.</p>
            </div>
          )}
          {chat.status === 'rejected' && (
            <div className="border-t border-red-200 bg-red-50 px-6 py-3 flex items-center gap-2 text-red-800">
              <ClipboardCheck className="w-4 h-4 shrink-0" />
              <p className="text-sm">This consultation has been rejected by a specialist.</p>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
