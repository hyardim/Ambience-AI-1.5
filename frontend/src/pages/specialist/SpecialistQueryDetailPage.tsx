import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
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
import { getErrorMessage, ifNotAbortError } from '../../utils/errors';
import { orFallback } from '../../utils/value';
import { runUnlessSilent } from '../../utils/control';
import { getCloseReviewTitle, getTerminalConsultationState } from '../../utils/specialist';
import {
  canAssignSpecialist,
  shouldAutoConnectSpecialistStream,
} from '../../utils/specialistQueryDetail';
import { SpecialistQueryDetailView } from './SpecialistQueryDetailView';

export function SpecialistQueryDetailPage() {
  const { username, logout } = useAuth();
  const { queryId } = useParams<{ queryId: string }>();
  const chatId = Number(queryId);
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
  const requestControllerRef = useRef<AbortController | null>(null);

  // ── Streaming state machine ────────────────────────────────────────────
  const refreshData = useCallback(async () => {
    try {
      const [profile, chatData] = await Promise.all([
        getProfile(),
        getSpecialistChatDetail(chatId),
      ]);
      setMyUserId(profile.id);
      setChat(chatData);
      setMessages(chatData.messages.map(m => toFrontendMessage(m, orFallback(username, 'Specialist User'), 'specialist')));
    } catch { /* silent refresh */ }
  }, [chatId, username]);

  const { phase: streamPhase, isStreaming: streamConnected, connectStream, startPolling, stopPolling } = useChatStream(
    setMessages,
    {
      chatId: chat?.id ?? null,
      onRefresh: refreshData,
      onFileContextTruncated: () => {
        setError(
          'Attached file context was truncated before AI revision. Ask for a shorter upload if key details are missing.',
        );
      },
    },
  );

  const loadData = useCallback(async (options?: { silent?: boolean }) => {
    const isSilent = options?.silent;
    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    runUnlessSilent(isSilent, () => {
      setLoading(true);
      setError('');
    });
    try {
      const [profile, chatData] = await Promise.all([
        getProfile({ signal: controller.signal }),
        getSpecialistChatDetail(chatId, { signal: controller.signal }),
      ]);
      setMyUserId(profile.id);
      setChat(chatData);
      setMessages(chatData.messages.map(m => toFrontendMessage(m, orFallback(username, 'Specialist User'), 'specialist')));
    } catch (err) {
      ifNotAbortError(err, () => {
        runUnlessSilent(isSilent, () => {
          setError(getErrorMessage(err, 'Failed to load consultation'));
        });
      });
    } finally {
      runUnlessSilent(isSilent, () => {
        setLoading(false);
      });
    }
  }, [chatId, username]);

  // Fetch profile (for specialist ID) + chat detail
  useEffect(() => {
    void loadData();
    return () => {
      requestControllerRef.current?.abort();
    };
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
    if (shouldPoll) {
      startPolling();
    } else {
      stopPolling();
    }
  }, [shouldPoll, startPolling, stopPolling]);

  // Auto-connect SSE when there's pending AI work and no active stream
  useEffect(() => {
    if (!chat) return;
    if (!shouldAutoConnectSpecialistStream({
      hasChat: true,
      streamConnected,
      streamPhase,
      hasPendingAIResponse,
      hasRevisionInProgress,
    })) return;

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
    const currentChat = chat!;
    setActionLoading(true);
    setError('');
    try {
      const updated = await assignChat(currentChat.id, myUserId!);
      setChat({ ...currentChat, ...updated });
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to assign chat'));
    } finally {
      setActionLoading(false);
    }
  };

  const handleApprove = async () => {
    const currentChat = chat!;
    setActionLoading(true);
    setError('');
    try {
      await reviewMessage(currentChat.id, reviewTargetMessageId!, 'approve');
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
    const currentChat = chat!;
    const targetMessageId = reviewTargetMessageId!;
    setActionLoading(true);
    setError('');
    try {
      await sendSpecialistMessage(currentChat.id, approveComment.trim());
      await reviewMessage(currentChat.id, targetMessageId, 'approve', approveComment.trim());
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
    const currentChat = chat!;
    const targetMessageId = reviewTargetMessageId!;
    setActionLoading(true);
    setError('');
    try {
      // Open SSE *before* the API call so we catch the revision stream events
      await connectStream(currentChat.id);
      await reviewMessage(currentChat.id, targetMessageId, 'request_changes', rejectReason.trim());
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
    const currentChat = chat!;
    const targetMessageId = reviewTargetMessageId!;
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
        await Promise.all(manualResponseFiles.map((file) => uploadChatFile(currentChat.id, file)));
      }
      const sources = manualResponseSources
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean);
      await reviewMessage(
        currentChat.id,
        targetMessageId,
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
    const currentChat = chat!;
    setActionLoading(true);
    setError('');
    try {
      await reviewChat(currentChat.id, 'approve');
      setShowCloseConfirm(false);
      await loadData();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to close consultation'));
    } finally {
      setActionLoading(false);
    }
  };

  const handleSendMessage = async (content: string, files?: File[]) => {
    const currentChat = chat!;
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
        await Promise.all(files.map(f => uploadChatFile(currentChat.id, f)));
      }
      await sendSpecialistMessage(currentChat.id, content);
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
  const canAssign = isSubmitted && canAssignSpecialist(myUserId);
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
  const closeReviewTitle = getCloseReviewTitle(anyGenerating, allAIReviewed) ?? '';
  const terminalState = getTerminalConsultationState(chatStatus);
  return (
    <SpecialistQueryDetailView
      username={username}
      logout={logout}
      chat={chat}
      messages={messages}
      loading={loading}
      error={error}
      actionLoading={actionLoading}
      canAssign={canAssign}
      canReview={canReview}
      isTerminal={isTerminal}
      hasPendingAIResponse={hasPendingAIResponse}
      allAIReviewed={allAIReviewed}
      closeReviewTitle={closeReviewTitle}
      terminalState={terminalState}
      unreviewedAIIds={unreviewedAIIds}
      approveComment={approveComment}
      rejectReason={rejectReason}
      manualResponseContent={manualResponseContent}
      manualResponseSources={manualResponseSources}
      manualResponseFiles={manualResponseFiles}
      showApproveConfirm={showApproveConfirm}
      showApproveWithCommentModal={showApproveWithCommentModal}
      showRejectModal={showRejectModal}
      showManualResponseModal={showManualResponseModal}
      showCloseConfirm={showCloseConfirm}
      messagesEndRef={messagesEndRef}
      onBack={() => navigate('/specialist/queries')}
      onAssign={handleAssign}
      onApprove={handleApprove}
      onApproveCommentChange={setApproveComment}
      onApproveWithComment={handleApproveWithComment}
      onRejectReasonChange={setRejectReason}
      onRequestChanges={handleRequestChanges}
      onManualResponseContentChange={setManualResponseContent}
      onManualResponseSourcesChange={setManualResponseSources}
      onManualResponseFilesChange={setManualResponseFiles}
      onManualResponse={handleManualResponse}
      onSendMessage={handleSendMessage}
      onOpenApproveConfirm={(messageId) => {
        setReviewTargetMessageId(Number(messageId));
        setShowApproveConfirm(true);
      }}
      onOpenApproveWithComment={(messageId) => {
        setReviewTargetMessageId(Number(messageId));
        setShowApproveWithCommentModal(true);
      }}
      onOpenRequestChanges={(messageId) => {
        setReviewTargetMessageId(Number(messageId));
        setShowRejectModal(true);
      }}
      onOpenManualResponse={(messageId) => {
        setReviewTargetMessageId(Number(messageId));
        setShowManualResponseModal(true);
      }}
      onCloseAndApprove={handleCloseAndApprove}
      onCloseApproveConfirm={() => setShowApproveConfirm(false)}
      onCloseApproveWithComment={() => {
        setShowApproveWithCommentModal(false);
        setApproveComment('');
      }}
      onCloseRejectModal={() => {
        setShowRejectModal(false);
        setRejectReason('');
      }}
      onCloseManualResponseModal={() => {
        setShowManualResponseModal(false);
        setManualResponseContent('');
        setManualResponseSources('');
        setManualResponseFiles([]);
      }}
      onOpenCloseConfirm={() => setShowCloseConfirm(true)}
      onCloseCloseConfirm={() => setShowCloseConfirm(false)}
    />
  );
}
