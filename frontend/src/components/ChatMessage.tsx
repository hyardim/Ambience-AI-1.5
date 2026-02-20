import { FileText, Bot, User } from 'lucide-react';
import type { Message } from '../types';

interface ChatMessageProps {
  message: Message;
  isOwnMessage?: boolean;
}

export function ChatMessage({ message, isOwnMessage = false }: ChatMessageProps) {
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

  return (
    <div className={`flex gap-3 sm:gap-4 ${isOwnMessage ? 'flex-row-reverse' : ''}`}>
      {/* Avatar */}
      <div className="shrink-0">
        <div className={`w-10 h-10 sm:w-12 sm:h-12 rounded-full flex items-center justify-center ${
          message.senderType === 'ai' ? 'bg-blue-100' : 'bg-gray-100'
        }`}>
          {getAvatarContent()}
        </div>
      </div>

      {/* Message content */}
      <div className={`flex-1 max-w-3xl ${isOwnMessage ? 'flex flex-col items-end' : ''}`}>
        {/* Header */}
        <div className={`flex items-center gap-2 sm:gap-3 mb-2 ${isOwnMessage ? 'flex-row-reverse' : ''}`}>
          <span className="font-semibold text-gray-900 text-sm sm:text-base">{getSenderLabel()}</span>
          <span className="text-xs sm:text-sm text-gray-500">{formatTime(message.timestamp)}</span>
        </div>

        {/* Message bubble */}
        <div className={`rounded-2xl px-4 sm:px-5 py-3 sm:py-4 ${
          isOwnMessage
            ? 'bg-[#e8edee] text-gray-900'
            : message.senderType === 'ai'
              ? 'bg-white border-l-4 border-[#005eb8] shadow-sm'
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
        </div>
      </div>
    </div>
  );
}
