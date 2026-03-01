import { FileText, Bot, User, CheckCircle, XCircle, Clock, RotateCcw } from 'lucide-react';
import type { Message } from '../types';

interface ChatMessageProps {
  message: Message;
  isOwnMessage?: boolean;
  /** Whether this message is part of a review workflow (show review badges on AI messages) */
  showReviewStatus?: boolean;
  /** Show inline specialist action buttons on this message */
  showReviewActions?: boolean;
  /** Callback when specialist clicks "Approve" on this message */
  onApprove?: () => void;
  /** Callback when specialist clicks "Request Changes" on this message */
  onRequestChanges?: () => void;
  /** Whether an action is currently loading */
  actionLoading?: boolean;
}

export function ChatMessage({
  message,
  isOwnMessage = false,
  showReviewStatus = false,
  showReviewActions = false,
  onApprove,
  onRequestChanges,
  actionLoading = false,
}: ChatMessageProps) {
  const formatTime = (date: Date) => {
    const today = new Date();
    const isToday = date.toDateString() === today.toDateString();
    const timeStr = date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });

    if (isToday) {
      return `Sent today at ${timeStr}`;
    }
    return `Sent ${date.toLocaleDateString('en-GB')} at ${timeStr}`;
  };

  const getAvatarContent = () => {
    if (message.senderType === 'ai') {
      return <Bot className="w-5 h-5 text-[#005eb8]" />;
    }
    return <User className="w-5 h-5 text-[#005eb8]" />;
  };

  const getSenderLabel = () => {
    if (message.senderType === 'ai') {
      return 'NHS AI Assistant';
    }
    return message.senderName;
  };

  const isAI = message.senderType === 'ai';
  const reviewStatus = message.reviewStatus;

  // Determine the border colour for AI messages based on review status
  const getAIBorderClass = () => {
    if (!isAI) return '';
    if (reviewStatus === 'approved') return 'border-l-4 border-[#007f3b]';
    if (reviewStatus === 'rejected') return 'border-l-4 border-[#da291c]';
    if (showReviewStatus && !reviewStatus) return 'border-l-4 border-amber-400';
    return 'border-l-4 border-[#005eb8]';
  };

  // Review status badge for AI messages
  const renderReviewBadge = () => {
    if (!isAI) return null;
    // Only show badge if the message has been reviewed, or if the parent opted in to show review status
    const hasExplicitStatus = !!reviewStatus;
    if (!hasExplicitStatus && !showReviewStatus) return null;

    if (reviewStatus === 'approved') {
      return (
        <span className="inline-flex items-center gap-1 text-xs font-medium text-green-700 bg-green-50 border border-green-200 rounded-full px-2.5 py-0.5">
          <CheckCircle className="w-3.5 h-3.5" />
          Specialist Approved
        </span>
      );
    }
    if (reviewStatus === 'rejected') {
      return (
        <span className="inline-flex items-center gap-1 text-xs font-medium text-red-700 bg-red-50 border border-red-200 rounded-full px-2.5 py-0.5">
          <XCircle className="w-3.5 h-3.5" />
          Changes Requested
        </span>
      );
    }
    // Pending review (no review_status yet)
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded-full px-2.5 py-0.5">
        <Clock className="w-3.5 h-3.5" />
        Awaiting Review
      </span>
    );
  };

  return (
    <div className={`flex gap-3 sm:gap-4 ${isOwnMessage ? 'flex-row-reverse' : ''}`}>
      {/* Avatar */}
      <div className="shrink-0">
        <div className={`w-10 h-10 sm:w-12 sm:h-12 rounded-full flex items-center justify-center ${
          message.senderType === 'ai'
            ? reviewStatus === 'approved'
              ? 'bg-green-100'
              : reviewStatus === 'rejected'
                ? 'bg-red-100'
                : 'bg-blue-100'
            : 'bg-gray-100'
        }`}>
          {getAvatarContent()}
        </div>
      </div>

      {/* Message content */}
      <div className={`flex-1 max-w-3xl ${isOwnMessage ? 'flex flex-col items-end' : ''}`}>
        {/* Header */}
        <div className={`flex items-center gap-2 sm:gap-3 mb-2 flex-wrap ${isOwnMessage ? 'flex-row-reverse' : ''}`}>
          <span className="font-semibold text-gray-900 text-sm sm:text-base">{getSenderLabel()}</span>
          <span className="text-xs sm:text-sm text-gray-500">{formatTime(message.timestamp)}</span>
          {renderReviewBadge()}
        </div>

        {/* Message bubble */}
        <div className={`rounded-2xl px-4 sm:px-5 py-3 sm:py-4 ${
          isOwnMessage
            ? 'bg-[#e8edee] text-gray-900'
            : isAI
              ? `bg-white ${getAIBorderClass()} shadow-sm`
              : 'bg-white shadow-sm'
        }`}>
          <div className="whitespace-pre-wrap text-gray-800 leading-relaxed text-sm sm:text-base">
            {message.content}
          </div>

          {/* Attachments */}
          {message.attachments && message.attachments.length > 0 && (
            <div className="mt-4 space-y-2">
              {message.attachments.map((file) => (
                <div
                  key={file.id}
                  className="flex items-center gap-3 bg-gray-100 rounded-lg px-4 py-3 hover:bg-gray-200 cursor-pointer transition-colors"
                >
                  <FileText className="w-5 h-5 text-[#005eb8]" />
                  <div>
                    <p className="font-medium text-gray-900 text-sm">{file.name}</p>
                    <p className="text-gray-500 text-xs">{file.size}</p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Guideline reference */}
          {message.guidelineReference && (
            <div className="mt-4 bg-blue-50 rounded-lg px-4 py-3 border-l-4 border-[#005eb8]">
              <p className="font-semibold text-[#005eb8] text-sm">{message.guidelineReference.title}</p>
              <p className="text-gray-600 text-sm">Reference No: {message.guidelineReference.referenceNo}</p>
              <p className="text-gray-500 text-xs italic mt-1">Last Updated: {message.guidelineReference.lastUpdated}</p>
            </div>
          )}

          {/* Review feedback (shown on rejected AI messages) */}
          {isAI && reviewStatus === 'rejected' && message.reviewFeedback && (
            <div className="mt-4 bg-red-50 rounded-lg px-4 py-3 border border-red-200">
              <p className="text-xs font-semibold text-red-700 mb-1">Specialist Feedback</p>
              <p className="text-sm text-red-800">{message.reviewFeedback}</p>
            </div>
          )}

          {/* Inline specialist review actions */}
          {showReviewActions && (
            <div className="mt-4 pt-3 border-t border-gray-200">
              <p className="text-xs text-gray-500 mb-2">Review this AI response:</p>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={onApprove}
                  disabled={actionLoading}
                  className="inline-flex items-center gap-1.5 bg-[#007f3b] text-white px-3.5 py-1.5 rounded-lg text-sm font-medium hover:bg-[#00662f] transition-colors disabled:opacity-50"
                >
                  <CheckCircle className="w-4 h-4" />
                  Approve
                </button>
                <button
                  onClick={onRequestChanges}
                  disabled={actionLoading}
                  className="inline-flex items-center gap-1.5 bg-amber-600 text-white px-3.5 py-1.5 rounded-lg text-sm font-medium hover:bg-amber-700 transition-colors disabled:opacity-50"
                >
                  <RotateCcw className="w-4 h-4" />
                  Request Changes
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
