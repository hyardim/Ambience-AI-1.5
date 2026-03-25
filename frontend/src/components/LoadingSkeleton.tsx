/**
 * Animated placeholder skeleton for loading states.
 * Renders pulsing gray bars to indicate content is loading.
 */
export function LoadingSkeleton({ lines = 3, className = '' }: { lines?: number; className?: string }) {
  return (
    <div className={`animate-pulse space-y-3 ${className}`} role="status" aria-label="Loading content">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="h-4 bg-gray-200 rounded" style={{ width: `${90 - i * 12}%` }} />
      ))}
      <span className="sr-only">Loading...</span>
    </div>
  );
}
