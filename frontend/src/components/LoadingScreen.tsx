import { Loader2 } from 'lucide-react';

export function LoadingScreen() {
  return (
    <div className="min-h-screen bg-[var(--nhs-page-bg)] flex items-center justify-center">
      <Loader2 className="w-8 h-8 text-[var(--nhs-blue)] animate-spin" />
    </div>
  );
}
