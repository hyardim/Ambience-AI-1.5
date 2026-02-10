import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { Header } from '../../components/Header';
import { ChatMessage } from '../../components/ChatMessage';
import { ChatInput } from '../../components/ChatInput';
import { StatusBadge, SeverityBadge } from '../../components/Badges';
import { mockQueries, mockGPNotifications } from '../../data/mockData';
import type { Message } from '../../types';

export function GPQueryDetailPage() {
  const { queryId } = useParams<{ queryId: string }>();
  const navigate = useNavigate();
  const query = mockQueries.find(q => q.id === queryId);
  const [messages, setMessages] = useState<Message[]>(query?.messages || []);

  if (!query) {
    return (
      <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
        <Header userRole="gp" userName="Dr. Sarah Johnson" notifications={mockGPNotifications} />
        <main className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <h1 className="text-2xl font-bold text-gray-900 mb-4">Query not found</h1>
            <button
              onClick={() => navigate('/gp/queries')}
              className="text-[#005eb8] hover:text-[#003087] font-medium"
            >
              Back to Queries
            </button>
          </div>
        </main>
      </div>
    );
  }

  const handleSendMessage = (content: string) => {
    const newMessage: Message = {
      id: `msg-${Date.now()}`,
      senderId: 'gp-1',
      senderName: 'Dr. Sarah Johnson',
      senderType: 'gp',
      content,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, newMessage]);
  };

  return (
    <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
      <Header userRole="gp" userName="Dr. Sarah Johnson" notifications={mockGPNotifications} />
      
      <main className="flex-1 max-w-5xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8 flex flex-col">
        {/* Back Button */}
        <button
          onClick={() => navigate('/gp/queries')}
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
                <h1 className="text-xl font-bold text-gray-900 mb-2">{query.title}</h1>
                <div className="flex flex-wrap items-center gap-3 text-sm text-gray-600">
                  <span className="font-medium">{query.gpName}</span>
                  <span>•</span>
                  <span className="capitalize">{query.specialty}</span>
                  <span>•</span>
                  <span>{new Date(query.createdAt).toLocaleDateString()}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <SeverityBadge severity={query.severity} />
                <StatusBadge status={query.status} />
              </div>
            </div>
          </div>

          {/* Chat Messages */}
          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            {messages.map(message => (
              <ChatMessage
                key={message.id}
                message={message}
                isOwnMessage={message.senderType === 'gp'}
              />
            ))}
          </div>

          {/* Chat Input */}
          {query.status !== 'resolved' && (
            <div className="border-t border-gray-200 p-4">
              <ChatInput onSendMessage={handleSendMessage} />
            </div>
          )}
        </div>
      </main>
    </div>
  );
}