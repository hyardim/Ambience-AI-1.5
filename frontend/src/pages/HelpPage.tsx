import { CheckCircle2, Info, TriangleAlert } from 'lucide-react';
import { Header } from '../components/Header';
import { useAuth } from '../contexts/useAuth';
import { orFallback } from '../utils/value';

type HelpRole = 'gp' | 'specialist';

interface HelpContent {
  workflowHeading: string;
  summary: string;
  steps: string[];
  features: string[];
  limitations: string[];
}

const HELP_CONTENT: Record<HelpRole, HelpContent> = {
  gp: {
    workflowHeading: 'GP Workflow',
    summary:
      'Use Ambience AI to structure your case, get an AI draft response, and track specialist review outcomes.',
    steps: [
      'Start in Queries and select New Consultation to create a case.',
      'Enter patient context, specialty, urgency, and a clear clinical question before submitting.',
      'Open the consultation detail page to review AI responses, citations, and conversation history.',
      'Use consultation statuses (Submitted, Under Review, Closed) to follow progress through specialist review.',
      'Archive completed consultations when they are no longer needed in your active list.',
    ],
    features: [
      'Search and filter consultations by text, specialty, and date.',
      'Update consultation metadata when details change.',
      'Attach supporting files to provide extra context for the model.',
      'Monitor notification updates when specialist actions occur.',
    ],
    limitations: [
      'The AI output is decision support, not a final diagnosis or treatment directive.',
      'Final clinical responsibility remains with the treating GP.',
      'Avoid sharing unnecessary identifying patient information.',
      'Escalate urgent or high-risk cases through established clinical safety processes.',
    ],
  },
  specialist: {
    workflowHeading: 'Specialist Workflow',
    summary:
      'Use Ambience AI to triage assigned work, review AI output quality, and send clinically safe specialist decisions.',
    steps: [
      'Open Queries for Review and monitor Queue and My Assigned tabs.',
      'Assign a consultation when you are taking ownership of the review.',
      'Inspect patient context, message history, and cited sources before deciding.',
      'Use review actions to approve, request changes, or provide a manual response with supporting rationale.',
      'Refresh and monitor statuses so no active consultations are left unresolved.',
    ],
    features: [
      'Sort and filter by status, severity, specialty, and creation date.',
      'Review consultation and message-level controls from the specialist detail page.',
      'Attach additional files and source references when manual responses are needed.',
      'Track pending workload with queue and assignment indicators.',
    ],
    limitations: [
      'AI drafts can be incomplete and must be clinically validated before approval.',
      'Specialist comments should be explicit when requesting revisions.',
      'Do not rely on unsupported claims that lack source evidence.',
      'Use existing trust escalation pathways for urgent safeguarding scenarios.',
    ],
  },
};

function resolveHelpRole(role: string | null): HelpRole {
  return role === 'specialist' ? 'specialist' : 'gp';
}

export function HelpPage() {
  const { role, username, logout } = useAuth();
  const helpRole = resolveHelpRole(role);
  const content = HELP_CONTENT[helpRole];

  return (
    <div className="min-h-screen bg-[var(--nhs-page-bg)] flex flex-col">
      <Header userRole={helpRole} userName={orFallback(username, 'User')} onLogout={logout} />

      <main className="flex-1 max-w-6xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        <section className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 sm:p-8">
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Help & Usage Guide</h1>
          <p className="mt-2 text-gray-700">{content.summary}</p>
        </section>

        <section className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 sm:p-8">
          <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 inline-flex items-center gap-2">
            <Info className="w-5 h-5 text-[var(--nhs-blue)]" />
            {content.workflowHeading}
          </h2>
          <ol className="mt-4 space-y-3 text-gray-800 list-decimal list-inside">
            {content.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </section>

        <section className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 sm:p-8">
          <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 inline-flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-green-700" />
            Key Features
          </h2>
          <ul className="mt-4 space-y-2 text-gray-800 list-disc list-inside">
            {content.features.map((feature) => (
              <li key={feature}>{feature}</li>
            ))}
          </ul>
        </section>

        <section className="bg-amber-50 rounded-xl shadow-sm border border-amber-200 p-6 sm:p-8">
          <h2 className="text-xl sm:text-2xl font-semibold text-amber-900 inline-flex items-center gap-2">
            <TriangleAlert className="w-5 h-5 text-amber-700" />
            Safety And Limitations
          </h2>
          <ul className="mt-4 space-y-2 text-amber-900 list-disc list-inside">
            {content.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        </section>
      </main>
    </div>
  );
}
