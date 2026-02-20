import { useNavigate } from 'react-router-dom';
import type { Query } from '../types';
import { StatusBadge, SeverityBadge } from './Badges';

interface QueryCardProps {
  query: Query;
  userRole: 'gp' | 'specialist';
}

export function QueryCard({ query, userRole }: QueryCardProps) {
  const navigate = useNavigate();
  const basePath = userRole === 'gp' ? '/gp' : '/specialist';

  const handleClick = () => {
    navigate(`${basePath}/query/${query.id}`);
  };

  const getPreviewText = () => {
    const lastMessage = query.messages[query.messages.length - 1];
    if (lastMessage) {
      const preview = lastMessage.content.substring(0, 100);
      return preview.length < lastMessage.content.length ? `${preview}...` : preview;
    }
    return query.description.substring(0, 100);
  };

  const formatSpecialty = (specialty: string) => {
    return specialty.charAt(0).toUpperCase() + specialty.slice(1);
  };

  return (
    <div
      onClick={handleClick}
      className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 hover:shadow-md hover:border-[#005eb8] cursor-pointer transition-all"
    >
      {/* Top row: Title + Specialty */}
      <div className="flex items-start justify-between gap-4 mb-1">
        <h3 className="font-semibold text-gray-900 text-base sm:text-lg flex-1 min-w-0">{query.title}</h3>
        <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs font-medium shrink-0">
          {formatSpecialty(query.specialty)}
        </span>
      </div>

      {/* Bottom row: Preview text on left, badges on right */}
      <div className="flex items-end justify-between gap-4">
        <div className="flex-1 min-w-0">
          <p className="text-gray-600 text-sm line-clamp-2">{getPreviewText()}</p>
          {userRole === 'specialist' && (
            <p className="text-gray-500 text-sm mt-1">From: {query.gpName}</p>
          )}
        </div>
        <div className="flex items-center gap-5 shrink-0">
          <SeverityBadge severity={query.severity} />
          <StatusBadge status={query.status} />
        </div>
      </div>
    </div>
  );
}
