export function getAdminChatDetailMessageClass(sender: string) {
  if (sender === 'ai') return 'bg-blue-50 border-l-4 border-[var(--nhs-blue)]';
  if (sender === 'specialist') return 'bg-green-50 border-l-4 border-[#007f3b]';
  return 'bg-gray-50';
}
