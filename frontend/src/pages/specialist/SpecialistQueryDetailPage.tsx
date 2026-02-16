import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, CheckCircle, XCircle, RotateCcw, AlertTriangle } from 'lucide-react';
import { Header } from '../../components/Header';
import { ChatMessage } from '../../components/ChatMessage';
import { ChatInput } from '../../components/ChatInput';
import { StatusBadge, SeverityBadge } from '../../components/Badges';
import { mockQueries, mockSpecialistNotifications } from '../../data/mockData';
import type { Message, QueryStatus } from '../../types';
import { useAuth } from '../../contexts/AuthContext';

export function SpecialistQueryDetailPage() {
  const { username, logout } = useAuth();
  const { queryId } = useParams<{ queryId: string }>();
  const navigate = useNavigate();
  const query = mockQueries.find(q => q.id === queryId);
  const [messages, setMessages] = useState<Message[]>(query?.messages || []);
  const [status, setStatus] = useState<QueryStatus>(query?.status || 'active');
  const [showApproveConfirm, setShowApproveConfirm] = useState(false);
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectReason, setRejectReason] = useState('');

  if (!query) {
    return (
      <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
        <Header userRole="specialist" userName={username || 'Specialist User'} notifications={mockSpecialistNotifications} onLogout={logout} />
        <main className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <h1 className="text-2xl font-bold text-gray-900 mb-4">Query not found</h1>
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

  const handleSendMessage = (content: string) => {
    const newMessage: Message = {
      id: `msg-${Date.now()}`,
      senderId: 'specialist-1',
      senderName: username || 'Specialist User',
      senderType: 'specialist',
      content,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, newMessage]);
  };

  const handleApprove = () => {
    setStatus('resolved');
    setShowApproveConfirm(false);
    const approvalMessage: Message = {
      id: `msg-${Date.now()}`,
      senderId: 'specialist-1',
      senderName: username || 'Specialist User',
      senderType: 'specialist',
      content: '✅ I have reviewed the AI response and approve this advice for the GP.',
      timestamp: new Date()
    };
    setMessages(prev => [...prev, approvalMessage]);
  };

  const handleReject = () => {
    if (rejectReason.trim()) {
      setStatus('pending-review');
      const rejectMessage: Message = {
        id: `msg-${Date.now()}`,
        senderId: 'specialist-1',
        senderName: username || 'Specialist User',
        senderType: 'specialist',
        content: `❌ The AI response requires modification: ${rejectReason}`,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, rejectMessage]);
      setShowRejectModal(false);
      setRejectReason('');
    }
  };

  const handleRetry = () => {
    setStatus('pending-review');
    const retryMessage: Message = {
      id: `msg-${Date.now()}`,
      senderId: 'specialist-1',
      senderName: username || 'Specialist User',
      senderType: 'specialist',
      content: '🔄 Requesting AI to regenerate the response with additional context.',
      timestamp: new Date()
    };
    setMessages(prev => [...prev, retryMessage]);
  };

  const canReview = status === 'active' || status === 'pending-review';

  return (
    <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
      <Header userRole="specialist" userName={username || 'Specialist User'} notifications={mockSpecialistNotifications} onLogout={logout} />
      
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
                <h1 className="text-xl font-bold text-gray-900 mb-2">{query.title}</h1>
                <div className="flex flex-wrap items-center gap-3 text-sm text-gray-600">
                  <span>From: {query.gpName}</span>
                  <span>•</span>
                  <span className="capitalize">{query.specialty}</span>
                  <span>•</span>
                  <span>{new Date(query.createdAt).toLocaleDateString()}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <SeverityBadge severity={query.severity} />
                <StatusBadge status={status} />
              </div>
            </div>

            {/* Action Buttons */}
            {canReview && (
              <div className="flex flex-wrap gap-3 mt-6 pt-4 border-t border-gray-200">
                <button
                  onClick={() => setShowApproveConfirm(true)}
                  className="inline-flex items-center gap-2 bg-[#007f3b] text-white px-4 py-2 rounded-lg font-medium hover:bg-[#00662f] transition-colors"
                >
                  <CheckCircle className="w-5 h-5" />
                  Approve Response
                </button>
                <button
                  onClick={() => setShowRejectModal(true)}
                  className="inline-flex items-center gap-2 bg-[#da291c] text-white px-4 py-2 rounded-lg font-medium hover:bg-[#b52217] transition-colors"
                >
                  <XCircle className="w-5 h-5" />
                  Request Changes
                </button>
                <button
                  onClick={handleRetry}
                  className="inline-flex items-center gap-2 bg-gray-100 text-gray-700 px-4 py-2 rounded-lg font-medium hover:bg-gray-200 transition-colors"
                >
                  <RotateCcw className="w-5 h-5" />
                  Regenerate AI Response
                </button>
              </div>
            )}
          </div>

          {/* Chat Messages */}
          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            {messages.map(message => (
              <ChatMessage
                key={message.id}
                message={message}
                isOwnMessage={message.senderType === 'specialist'}
              />
            ))}
          </div>

          {/* Chat Input */}
          {status !== 'resolved' && (
            <div className="border-t border-gray-200 p-4">
              <ChatInput onSendMessage={handleSendMessage} placeholder="Add a comment or ask for clarification..." />
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
                className="px-4 py-2 bg-[#007f3b] text-white rounded-lg font-medium hover:bg-[#00662f]"
              >
                Confirm Approval
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
                onClick={handleReject}
                disabled={!rejectReason.trim()}
                className="px-4 py-2 bg-amber-600 text-white rounded-lg font-medium hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Submit Feedback
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}