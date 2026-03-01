import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, CheckCircle, XCircle, AlertTriangle,
  Loader2, UserPlus,
} from 'lucide-react';
import { Header } from '../../components/Header';
import { ChatMessage } from '../../components/ChatMessage';
import { ChatInput } from '../../components/ChatInput';
import { StatusBadge, SeverityBadge } from '../../components/Badges';
import { useAuth } from '../../contexts/AuthContext';
import {
  getSpecialistChatDetail,
  getProfile,
  assignChat,
  reviewChat,
  sendSpecialistMessage,
} from '../../services/api';
import type { BackendChatWithMessages, BackendMessage } from '../../types/api';
import type { Message } from '../../types';

/** Map a backend message to the frontend Message shape used by ChatMessage */
function toFrontendMessage(msg: BackendMessage, currentUser: string): Message {
  const isAI = msg.sender === 'ai';
  const isSpecialist = msg.sender === 'specialist';
  return {
    id: String(msg.id),
    senderId: msg.sender,
    senderName: isAI ? 'NHS AI Assistant' : isSpecialist ? currentUser : 'GP User',
    senderType: isAI ? 'ai' : isSpecialist ? 'specialist' : 'gp',
    content: msg.content,
    timestamp: new Date(msg.created_at),
    reviewStatus: msg.review_status ?? null,
    reviewFeedback: msg.review_feedback ?? null,
    reviewedAt: msg.reviewed_at ?? null,
  };
}

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
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectReason, setRejectReason] = useState('');

  const [myUserId, setMyUserId] = useState<number | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Fetch profile (for specialist ID) + chat detail
  useEffect(() => {
    loadData();
  }, [queryId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const loadData = async () => {
    if (!queryId) return;
    setLoading(true);
    setError('');
    try {
      const [profile, chatData] = await Promise.all([
        getProfile(),
        getSpecialistChatDetail(Number(queryId)),
      ]);
      setMyUserId(profile.id);
      setChat(chatData);
      setMessages(chatData.messages.map(m => toFrontendMessage(m, username || 'Specialist User')));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load consultation');
    } finally {
      setLoading(false);
    }
  };

  // ── Actions ──────────────────────────────────────────────────

  const handleAssign = async () => {
    if (!chat || myUserId === null) return;
    setActionLoading(true);
    setError('');
    try {
      const updated = await assignChat(chat.id, myUserId);
      setChat(prev => (prev ? { ...prev, ...updated } : prev));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to assign chat');
    } finally {
      setActionLoading(false);
    }
  };

  const handleApprove = async () => {
    if (!chat) return;
    setActionLoading(true);
    setError('');
    try {
      const updated = await reviewChat(chat.id, 'approve');
      setChat(prev => (prev ? { ...prev, ...updated } : prev));
      setShowApproveConfirm(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to approve');
    } finally {
      setActionLoading(false);
    }
  };

  const handleRequestChanges = async () => {
    if (!chat || !rejectReason.trim()) return;
    setActionLoading(true);
    setError('');
    try {
      await reviewChat(chat.id, 'request_changes', rejectReason.trim());
      setShowRejectModal(false);
      setRejectReason('');
      // Reload full chat data to see the regenerated AI response
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to request changes');
    } finally {
      setActionLoading(false);
    }
  };

  const handleSendMessage = async (content: string) => {
    if (!chat) return;
    // Optimistically add the specialist message
    const tempId = `temp-${Date.now()}`;
    const optimistic: Message = {
      id: tempId,
      senderId: 'specialist',
      senderName: username || 'Specialist User',
      senderType: 'specialist',
      content,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, optimistic]);

    try {
      await sendSpecialistMessage(chat.id, content);
    } catch (err) {
      // Remove the optimistic message on failure
      setMessages(prev => prev.filter(m => m.id !== tempId));
      setError(err instanceof Error ? err.message : 'Failed to send message');
    }
  };

  // ── Derived state ────────────────────────────────────────────

  const chatStatus = chat?.status ?? '';
  const isSubmitted = chatStatus === 'submitted';
  const isAssignedOrReviewing = chatStatus === 'assigned' || chatStatus === 'reviewing';
  const isTerminal = ['approved', 'rejected', 'closed'].includes(chatStatus);
  const canAssign = isSubmitted;
  const canReview = isAssignedOrReviewing;

  // Find the latest AI message that hasn't been reviewed yet
  const latestUnreviewedAIId = (() => {
    const aiMessages = messages.filter(m => m.senderType === 'ai' && !m.reviewStatus);
    return aiMessages.length > 0 ? aiMessages[aiMessages.length - 1].id : null;
  })();

  const formatSpecialty = (s: string | null) =>
    s ? s.charAt(0).toUpperCase() + s.slice(1) : '—';

  // ── Loading / not-found states ───────────────────────────────

  if (loading) {
    return (
      <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
        <Header userRole="specialist" userName={username || 'Specialist User'} onLogout={logout} />
        <main className="flex-1 flex items-center justify-center">
          <Loader2 className="w-8 h-8 text-[#005eb8] animate-spin" />
        </main>
      </div>
    );
  }

  if (!chat) {
    return (
      <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
        <Header userRole="specialist" userName={username || 'Specialist User'} onLogout={logout} />
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
      <Header userRole="specialist" userName={username || 'Specialist User'} onLogout={logout} />

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
                <div className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-gray-600 bg-gray-50 border border-gray-200">
                  Review actions are available on each AI response below.
                </div>
              )}

              {/* Terminal status banner */}
              {isTerminal && (
                <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium ${
                  chatStatus === 'approved'
                    ? 'bg-green-50 text-green-700'
                    : 'bg-red-50 text-red-700'
                }`}>
                  {chatStatus === 'approved' ? (
                    <><CheckCircle className="w-5 h-5" /> Consultation Approved</>
                  ) : (
                    <><XCircle className="w-5 h-5" /> Consultation Rejected</>
                  )}
                  {chat.review_feedback && (
                    <span className="ml-2 font-normal">— {chat.review_feedback}</span>
                  )}
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
                // The latest AI message without a review status is the one the specialist should act on
                const isLatestUnreviewedAI =
                  canReview &&
                  message.senderType === 'ai' &&
                  !message.reviewStatus &&
                  message.id === latestUnreviewedAIId;

                return (
                  <ChatMessage
                    key={message.id}
                    message={message}
                    isOwnMessage={message.senderType === 'specialist'}
                    showReviewStatus={canReview || isTerminal}
                    showReviewActions={isLatestUnreviewedAI}
                    onApprove={() => setShowApproveConfirm(true)}
                    onRequestChanges={() => setShowRejectModal(true)}
                    actionLoading={actionLoading}
                  />
                );
              })
            )}
            <div ref={messagesEndRef} />
          </div>

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
    </div>
  );
}
