import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, CheckCircle, AlertTriangle,
  Loader2, UserPlus, MessageSquare, PenLine, Lock,
} from 'lucide-react';
import { Header } from '../../components/Header';
import { ChatMessage } from '../../components/ChatMessage';
import { ChatInput } from '../../components/ChatInput';
import { StatusBadge, SeverityBadge } from '../../components/Badges';
import { useAuth } from '../../contexts/useAuth';
import { useChatStream } from '../../hooks/useChatStream';
import { toFrontendMessage } from '../../utils/messageMapping';
import {
  getSpecialistChatDetail,
  getProfile,
  assignChat,
  reviewChat,
  reviewMessage,
  sendSpecialistMessage,
  uploadChatFile,
} from '../../services/api';
import type { BackendChatWithMessages } from '../../types/api';
import type { Message } from '../../types';
import { getErrorMessage } from '../../utils/errors';
import { orFallback } from '../../utils/value';
import { filesFromInput, runUnlessSilent } from '../../utils/control';
import { getCloseReviewTitle, getTerminalConsultationState } from '../../utils/specialist';

export function SpecialistQueryDetailPage() {
  const { username, logout } = useAuth();
  const { queryId } = useParams<{ queryId: string }>();
  const navigate = useNavigate();

  const [chat, setChat] = useState<BackendChatWithMessages | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  const [showApproveConfirm, setShowApproveConfirm] = useState(false);
  const [showApproveWithCommentModal, setShowApproveWithCommentModal] = useState(false);
  const [approveComment, setApproveComment] = useState('');
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [showManualResponseModal, setShowManualResponseModal] = useState(false);
  const [manualResponseContent, setManualResponseContent] = useState('');
  const [manualResponseSources, setManualResponseSources] = useState('');
  const [manualResponseFiles, setManualResponseFiles] = useState<File[]>([]);
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);

  // Which message the current modal action targets
  const [reviewTargetMessageId, setReviewTargetMessageId] = useState<number | null>(null);

  const [myUserId, setMyUserId] = useState<number | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // ── Streaming state machine ────────────────────────────────────────────
  const refreshData = useCallback(async () => {
    /* v8 ignore next */
    /* v8 ignore next */
    if (!queryId) return;
    try {
      const [profile, chatData] = await Promise.all([
        getProfile(),
        getSpecialistChatDetail(Number(queryId)),
      ]);
      setMyUserId(profile.id);
      setChat(chatData);
      setMessages(chatData.messages.map(m => toFrontendMessage(m, orFallback(username, 'Specialist User'), 'specialist')));
    /* v8 ignore next */
    } catch { /* silent refresh */ }
  }, [queryId, username]);

  const { phase: streamPhase, isStreaming: streamConnected, connectStream, startPolling, stopPolling } = useChatStream(
    setMessages,
    { chatId: chat?.id ?? null, onRefresh: refreshData },
  );

  const loadData = useCallback(async (options?: { silent?: boolean }) => {
    /* v8 ignore next */
    /* v8 ignore next */
    if (!queryId) return;
    const isSilent = options?.silent;
    runUnlessSilent(isSilent, () => {
      setLoading(true);
      setError('');
    });
    try {
      const [profile, chatData] = await Promise.all([
        getProfile(),
        getSpecialistChatDetail(Number(queryId)),
      ]);
      setMyUserId(profile.id);
      setChat(chatData);
      setMessages(chatData.messages.map(m => toFrontendMessage(m, orFallback(username, 'Specialist User'), 'specialist')));
    } catch (err) {
      runUnlessSilent(isSilent, () => {
        setError(getErrorMessage(err, 'Failed to load consultation'));
      });
    } finally {
      runUnlessSilent(isSilent, () => {
        setLoading(false);
      });
    }
  }, [queryId, username]);

  // Fetch profile (for specialist ID) + chat detail
  useEffect(() => {
    void loadData();
  }, [loadData]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  const hasPendingAIResponse =
    messages.length > 0 && messages[messages.length - 1].senderType === 'gp';

  // True when the last AI message is still being revised by the RAG service
  const hasRevisionInProgress =
    messages.length > 0 &&
    messages[messages.length - 1].senderType === 'ai' &&
    messages[messages.length - 1].isGenerating === true;

  // Only poll when SSE is not connected and there's pending work
  const shouldPoll = (hasPendingAIResponse || hasRevisionInProgress) && !streamConnected;

  // Delegate polling to the hook
  useEffect(() => {
    /* v8 ignore next */
    /* v8 ignore next */
    if (!queryId) return;
    if (shouldPoll) {
      startPolling();
    } else {
      stopPolling();
    }
  }, [queryId, shouldPoll, startPolling, stopPolling]);

  // Auto-connect SSE when there's pending AI work and no active stream
  useEffect(() => {
    /* v8 ignore next */
    if (!chat) return;
    /* v8 ignore next */
    if (streamConnected) return;
    /* v8 ignore next */
    if (streamPhase !== 'idle' && streamPhase !== 'fallback_polling') return;
    if (!(hasPendingAIResponse || hasRevisionInProgress)) return;

    void connectStream(chat.id);
  }, [
    chat,
    connectStream,
    hasPendingAIResponse,
    hasRevisionInProgress,
    streamConnected,
    streamPhase,
  ]);

  // ── Actions ──────────────────────────────────────────────────

  const handleAssign = async () => {
    /* v8 ignore next */
    if (!chat || myUserId === null) return;
    setActionLoading(true);
    setError('');
    try {
      const updated = await assignChat(chat.id, myUserId);
      setChat({ ...chat, ...updated });
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to assign chat'));
    } finally {
      setActionLoading(false);
    }
  };

  const handleApprove = async () => {
    /* v8 ignore next */
    if (!chat || reviewTargetMessageId === null) return;
    setActionLoading(true);
    setError('');
    try {
      await reviewMessage(chat.id, reviewTargetMessageId, 'approve');
      setShowApproveConfirm(false);
      setReviewTargetMessageId(null);
      await loadData();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to approve'));
    } finally {
      setActionLoading(false);
    }
  };

  const handleApproveWithComment = async () => {
    /* v8 ignore next */
    if (!chat || !approveComment.trim() || reviewTargetMessageId === null) return;
    setActionLoading(true);
    setError('');
    try {
      await sendSpecialistMessage(chat.id, approveComment.trim());
      await reviewMessage(chat.id, reviewTargetMessageId, 'approve', approveComment.trim());
      setShowApproveWithCommentModal(false);
      setApproveComment('');
      setReviewTargetMessageId(null);
      await loadData();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to approve'));
    } finally {
      setActionLoading(false);
    }
  };

  const handleRequestChanges = async () => {
    /* v8 ignore next */
    if (!chat || !rejectReason.trim() || reviewTargetMessageId === null) return;
    setActionLoading(true);
    setError('');
    try {
      // Open SSE *before* the API call so we catch the revision stream events
      await connectStream(chat.id);
      await reviewMessage(chat.id, reviewTargetMessageId, 'request_changes', rejectReason.trim());
      setShowRejectModal(false);
      setRejectReason('');
      setReviewTargetMessageId(null);
      // Reconcile with persisted state (streaming will update progressively)
      await loadData({ silent: true });
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to request changes'));
    } finally {
      setActionLoading(false);
    }
  };

  const handleManualResponse = async () => {
    /* v8 ignore next */
    if (!chat || !manualResponseContent.trim() || reviewTargetMessageId === null) return;
    setActionLoading(true);
    setError('');
    try {
      const MAX_FILE_SIZE = 3 * 1024 * 1024;
      const oversized = manualResponseFiles.filter((file) => file.size > MAX_FILE_SIZE);
      if (oversized.length > 0) {
        setError(`File(s) too large: ${oversized.map((file) => file.name).join(', ')}. Maximum size is 3 MB.`);
        return;
      }
      if (manualResponseFiles.length > 0) {
        await Promise.all(manualResponseFiles.map((file) => uploadChatFile(chat.id, file)));
      }
      const sources = manualResponseSources
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean);
      await reviewMessage(
        chat.id,
        reviewTargetMessageId,
        'manual_response',
        undefined,
        manualResponseContent.trim(),
        sources,
      );
      setShowManualResponseModal(false);
      setManualResponseContent('');
      setManualResponseSources('');
      setManualResponseFiles([]);
      setReviewTargetMessageId(null);
      await loadData();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to submit manual response'));
    } finally {
      setActionLoading(false);
    }
  };

  const handleCloseAndApprove = async () => {
    /* v8 ignore next */
    if (!chat) return;
    setActionLoading(true);
    setError('');
    try {
      await reviewChat(chat.id, 'approve');
      setShowCloseConfirm(false);
      await loadData();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to close consultation'));
    } finally {
      setActionLoading(false);
    }
  };

  const handleSendMessage = async (content: string, files?: File[]) => {
    /* v8 ignore next */
    if (!chat) return;
    // Optimistically add the specialist message
    const tempId = `temp-${Date.now()}`;
    const optimistic: Message = {
      id: tempId,
      senderId: 'specialist',
      senderName: orFallback(username, 'Specialist User'),
      senderType: 'specialist',
      content,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, optimistic]);

    const MAX_FILE_SIZE = 3 * 1024 * 1024; // 3 MB
    try {
      if (files && files.length > 0) {
        const oversized = files.filter(f => f.size > MAX_FILE_SIZE);
        if (oversized.length > 0) {
          setMessages(prev => prev.filter(m => m.id !== tempId));
          setError(`File(s) too large: ${oversized.map(f => f.name).join(', ')}. Maximum size is 3 MB.`);
          return;
        }
        await Promise.all(files.map(f => uploadChatFile(chat.id, f)));
      }
      await sendSpecialistMessage(chat.id, content);
    } catch (err) {
      // Remove the optimistic message on failure
      setMessages(prev => prev.filter(m => m.id !== tempId));
      setError(getErrorMessage(err, 'Failed to send message'));
    }
  };

  // ── Derived state ────────────────────────────────────────────

  const chatStatus = chat?.status ?? '';
  const isSubmitted = chatStatus === 'submitted';
  const isAssignedOrReviewing = chatStatus === 'assigned' || chatStatus === 'reviewing';
  const isTerminal = ['approved', 'rejected', 'closed'].includes(chatStatus);
  const canAssign = isSubmitted;
  const canReview = isAssignedOrReviewing;

  // IDs of all unreviewed AI messages (specialist can act on any of them)
  // Exclude messages still being generated — no actions should be shown on those.
  const unreviewedAIIds = new Set(
    messages.filter(m => m.senderType === 'ai' && !m.reviewStatus && !m.isGenerating).map(m => m.id)
  );

  // Whether every AI message has been reviewed (approved or rejected)
  // Also prevent closing if any message is still being generated.
  const aiMessages = messages.filter(m => m.senderType === 'ai');
  const anyGenerating = aiMessages.some(m => m.isGenerating);
  const allAIReviewed = aiMessages.length > 0 && unreviewedAIIds.size === 0 && !anyGenerating;
  const closeReviewTitle = getCloseReviewTitle(anyGenerating, allAIReviewed);
  const terminalState = getTerminalConsultationState(chatStatus);
  const TerminalStatusIcon = terminalState.icon;

  const formatSpecialty = (s: string | null) =>
    s ? s.charAt(0).toUpperCase() + s.slice(1) : '—';

  // ── Loading / not-found states ───────────────────────────────

  if (loading) {
    return (
      <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
        <Header userRole="specialist" userName={orFallback(username, 'Specialist User')} onLogout={logout} />
        <main className="flex-1 flex items-center justify-center">
          <Loader2 className="w-8 h-8 text-[#005eb8] animate-spin" />
        </main>
      </div>
    );
  }

  if (!chat) {
    return (
      <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
        <Header userRole="specialist" userName={orFallback(username, 'Specialist User')} onLogout={logout} />
        <main className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <h1 className="text-2xl font-bold text-gray-900 mb-2">Query not found</h1>
            {error && <p className="text-red-600 mb-4">{error}</p>}
            <button
              onClick={() => navigate('/specialist/queries')}
              className="text-[#005eb8] hover:text-[#003087] font-medium"
            >
              Back to Queries
            </button>
          </div>
        </main>
      </div>
    );
  }

  // ── Render ───────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
      <Header userRole="specialist" userName={orFallback(username, 'Specialist User')} onLogout={logout} />

      <main className="flex-1 max-w-5xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8 flex flex-col">
        {/* Back Button */}
        <button
          onClick={() => navigate('/specialist/queries')}
          className="inline-flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-6"
        >
          <ArrowLeft className="w-5 h-5" />
          Back to Queries
        </button>

        <div className="bg-white rounded-xl shadow-sm flex-1 flex flex-col overflow-hidden">
          {/* Query Header */}
          <div className="p-6 border-b border-gray-200">
            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
              <div className="flex-1">
                <h1 className="text-xl font-bold text-gray-900 mb-2">
                  {chat.title || 'Untitled Consultation'}
                </h1>
                <div className="flex flex-wrap items-center gap-3 text-sm text-gray-600">
                  <span className="capitalize">{formatSpecialty(chat.specialty)}</span>
                  <span>·</span>
                  <span>
                    {new Date(chat.created_at).toLocaleDateString('en-GB', {
                      day: 'numeric', month: 'short', year: 'numeric',
                    })}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {chat.severity && <SeverityBadge severity={chat.severity} />}
                <StatusBadge status={chat.status} />
              </div>
            </div>

            {/* Error */}
            {error && (
              <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                {error}
              </div>
            )}

            {/* Action area */}
            <div className="flex flex-wrap gap-3 mt-6 pt-4 border-t border-gray-200">
              {/* Assign button */}
              {canAssign && (
                <button
                  onClick={handleAssign}
                  disabled={actionLoading}
                  className="inline-flex items-center gap-2 bg-[#005eb8] text-white px-4 py-2 rounded-lg font-medium hover:bg-[#003087] transition-colors disabled:opacity-50"
                >
                  <UserPlus className="w-5 h-5" />
                  {actionLoading ? 'Assigning…' : 'Assign to Me'}
                </button>
              )}

              {/* Hint when reviewing — actions are on messages */}
              {canReview && (
                <>
                  <div className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-gray-600 bg-gray-50 border border-gray-200">
                    Review actions are available on each AI response below.
                  </div>
                  {/* v8 ignore next */}
                  <button
                    onClick={() => setShowCloseConfirm(true)}
                    disabled={actionLoading || !allAIReviewed}
                    title={closeReviewTitle}
                    className="inline-flex items-center gap-2 bg-[#007f3b] text-white px-4 py-2 rounded-lg font-medium hover:bg-[#00662f] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <Lock className="w-5 h-5" />
                    Close &amp; Approve Consultation
                  </button>
                </>
              )}

              {/* Terminal status banner */}
              {isTerminal && (
                <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium ${terminalState.className}`}>
                  <TerminalStatusIcon className="w-5 h-5" />
                  {terminalState.label}
                </div>
              )}
            </div>
          </div>

          {/* Chat Messages */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {messages.length === 0 ? (
              <p className="text-center text-gray-500 py-8">No messages yet.</p>
            ) : (
              messages.map(message => {
                const isUnreviewedAI = canReview && unreviewedAIIds.has(message.id);

                return (
                  <ChatMessage
                    key={message.id}
                    message={message}
                    isOwnMessage={message.senderType === 'specialist'}
                    showReviewStatus={canReview || isTerminal}
                    showReviewActions={isUnreviewedAI}
                    onApprove={() => {
                      setReviewTargetMessageId(Number(message.id));
                      setShowApproveConfirm(true);
                    }}
                    onApproveWithComment={() => {
                      setReviewTargetMessageId(Number(message.id));
                      setShowApproveWithCommentModal(true);
                    }}
                    onRequestChanges={() => {
                      setReviewTargetMessageId(Number(message.id));
                      setShowRejectModal(true);
                    }}
                    onManualResponse={() => {
                      setReviewTargetMessageId(Number(message.id));
                      setShowManualResponseModal(true);
                    }}
                    actionLoading={actionLoading}
                  />
                );
              })
            )}
            {hasPendingAIResponse && (
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

          {/* All reviewed — bottom close banner */}
          {canReview && allAIReviewed && (
            <div className="border-t border-gray-200 bg-green-50 p-4 flex items-center justify-between">
              <div className="flex items-center gap-2 text-green-700 text-sm font-medium">
                <CheckCircle className="w-5 h-5" />
                All AI responses have been reviewed.
              </div>
              <button
                onClick={() => setShowCloseConfirm(true)}
                disabled={actionLoading}
                className="inline-flex items-center gap-2 bg-[#007f3b] text-white px-4 py-2 rounded-lg font-medium hover:bg-[#00662f] transition-colors disabled:opacity-50"
              >
                <Lock className="w-5 h-5" />
                Close &amp; Approve Consultation
              </button>
            </div>
          )}

          {/* Chat Input (disabled for terminal states) */}
          {!isTerminal && (
            <div className="border-t border-gray-200 p-4">
              <ChatInput
                onSendMessage={handleSendMessage}
                placeholder="Add a comment or ask for clarification..."
              />
            </div>
          )}
        </div>
      </main>

      {/* Approve Confirmation Modal */}
      {showApproveConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6">
            <div className="flex items-center gap-3 text-[#007f3b] mb-4">
              <CheckCircle className="w-8 h-8" />
              <h2 className="text-xl font-bold">Approve Response</h2>
            </div>
            <p className="text-gray-600 mb-6">
              By approving, you confirm that the AI-generated response is clinically accurate
              and appropriate to send to the GP.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowApproveConfirm(false)}
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 font-medium hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleApprove}
                disabled={actionLoading}
                className="px-4 py-2 bg-[#007f3b] text-white rounded-lg font-medium hover:bg-[#00662f] disabled:opacity-50"
              >
                {actionLoading ? 'Approving…' : 'Confirm Approval'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Approve with Comment Modal */}
      {showApproveWithCommentModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6">
            <div className="flex items-center gap-3 text-[#005eb8] mb-4">
              <MessageSquare className="w-8 h-8" />
              <h2 className="text-xl font-bold">Approve with Comment</h2>
            </div>
            <p className="text-gray-600 mb-4">
              Your comment will be sent as a message to the GP before the consultation is approved.
            </p>
            <textarea
              value={approveComment}
              onChange={(e) => setApproveComment(e.target.value)}
              rows={4}
              autoFocus
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent resize-none mb-6"
              placeholder="Add your comment for the GP..."
            />
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => {
                  setShowApproveWithCommentModal(false);
                  setApproveComment('');
                }}
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 font-medium hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleApproveWithComment}
                disabled={!approveComment.trim() || actionLoading}
                className="px-4 py-2 bg-[#005eb8] text-white rounded-lg font-medium hover:bg-[#003087] disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {actionLoading ? 'Approving…' : 'Send & Approve'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reject Modal */}
      {showRejectModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6">
            <div className="flex items-center gap-3 text-amber-600 mb-4">
              <AlertTriangle className="w-8 h-8" />
              <h2 className="text-xl font-bold">Request Changes</h2>
            </div>
            <p className="text-gray-600 mb-4">
              Please describe what changes are needed to the AI response:
            </p>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              rows={4}
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent resize-none mb-6"
              placeholder="Describe the required changes..."
            />
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => {
                  setShowRejectModal(false);
                  setRejectReason('');
                }}
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 font-medium hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleRequestChanges}
                disabled={!rejectReason.trim() || actionLoading}
                className="px-4 py-2 bg-amber-600 text-white rounded-lg font-medium hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {actionLoading ? 'Submitting…' : 'Submit Feedback'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Manual Response Modal */}
      {showManualResponseModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6">
            <div className="flex items-center gap-3 text-purple-600 mb-4">
              <PenLine className="w-8 h-8" />
              <h2 className="text-xl font-bold">Manual Response</h2>
            </div>
            <p className="text-gray-600 mb-4">
              The AI response will be rejected. Type your replacement response below —
              it will be sent to the GP as a specialist message.
            </p>
            <textarea
              value={manualResponseContent}
              onChange={(e) => setManualResponseContent(e.target.value)}
              rows={6}
              autoFocus
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none"
              placeholder="Type your replacement response..."
            />
            <div className="mt-4 mb-6">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Sources
              </label>
              <textarea
                value={manualResponseSources}
                onChange={(e) => setManualResponseSources(e.target.value)}
                rows={4}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none"
                placeholder="Optional. Add one source per line."
              />
            </div>
            <div className="mt-4 mb-6">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Attach files
              </label>
              {/* v8 ignore next */}
              <input
                type="file"
                multiple
                accept=".pdf,.txt,.md,.rtf"
                onChange={(e) => setManualResponseFiles(filesFromInput(e.target.files))}
                className="block w-full text-sm text-gray-600 file:mr-4 file:rounded-lg file:border-0 file:bg-purple-50 file:px-4 file:py-2 file:font-medium file:text-purple-700 hover:file:bg-purple-100"
              />
              {manualResponseFiles.length > 0 && (
                <p className="mt-2 text-sm text-gray-500">
                  {manualResponseFiles.length} file(s) will be uploaded to this chat before the manual response is sent.
                </p>
              )}
            </div>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => {
                  setShowManualResponseModal(false);
                  setManualResponseContent('');
                  setManualResponseSources('');
                  setManualResponseFiles([]);
                }}
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 font-medium hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleManualResponse}
                disabled={!manualResponseContent.trim() || actionLoading}
                className="px-4 py-2 bg-purple-600 text-white rounded-lg font-medium hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {actionLoading ? 'Sending…' : 'Send Manual Response'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Close & Approve Confirmation Modal */}
      {showCloseConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6">
            <div className="flex items-center gap-3 text-[#007f3b] mb-4">
              <Lock className="w-8 h-8" />
              <h2 className="text-xl font-bold">Close & Approve Consultation</h2>
            </div>
            <p className="text-gray-600 mb-6">
              This will close the consultation and mark it as approved. The GP will be
              notified that the review is complete. This action cannot be undone.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowCloseConfirm(false)}
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 font-medium hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleCloseAndApprove}
                disabled={actionLoading}
                className="px-4 py-2 bg-[#007f3b] text-white rounded-lg font-medium hover:bg-[#00662f] disabled:opacity-50"
              >
                {actionLoading ? 'Closing…' : 'Confirm Close & Approve'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
