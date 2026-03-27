import { CheckCircle2, Info, TriangleAlert } from 'lucide-react';
import { Header } from '../components/Header';
import { useAuth } from '../contexts/useAuth';
import { orFallback } from '../utils/value';

type HelpRole = 'gp' | 'specialist';

interface HelpStep {
  title: string;
  bullets: string[];
}

interface HelpContent {
  workflowHeading: string;
  summary: string;
  steps: HelpStep[];
  features: string[];
  limitations: string[];
}

const HELP_CONTENT: Record<HelpRole, HelpContent> = {
  gp: {
    workflowHeading: 'GP Workflow',
    summary:
      'Use Ambience AI to create a case, get a draft answer, and follow specialist feedback.',
    steps: [
      {
        title: 'Step 1: Create the consultation',
        bullets: [
          'Start in Queries and select New Consultation to create a case.',
          'Enter patient context, specialty, urgency, and a clear clinical question before submitting.',
        ],
      },
      {
        title: 'Step 2: Review the consultation detail',
        bullets: [
          'Open the consultation detail page to review AI responses, citations, and conversation history.',
          'Use follow-up messages to ask for missing details before making a decision.',
        ],
      },
      {
        title: 'Step 3: Track specialist review progress',
        bullets: [
          'Use consultation statuses (Submitted, Under Review, Closed) to follow progress through specialist review.',
          'Check notifications when specialist actions occur on your consultation.',
        ],
      },
      {
        title: 'Step 4: Close out completed work',
        bullets: [
          'Archive completed consultations when they are no longer needed in your active list.',
          'Record important outcomes in your local notes as needed.',
        ],
      },
    ],
    features: [
      'Search and filter consultations by text, specialty, and date.',
      'Update consultation metadata when details change.',
      'Attach supporting files to provide extra context for the model.',
      'Monitor notification updates when specialist actions occur.',
    ],
    limitations: [
      'AI responses are support only and are not a final diagnosis or treatment plan.',
      'The GP remains responsible for final clinical decisions.',
      'Do not add unnecessary identifying patient details.',
      'Use your normal urgent-care process for high-risk cases.',
    ],
  },
  specialist: {
    workflowHeading: 'Specialist Workflow',
    summary:
      'Use Ambience AI to review assigned cases, check draft quality, and send safe final advice.',
    steps: [
      {
        title: 'Step 1: Check new consultations',
        bullets: [
          'Open Queries for Review and check Queue and My Assigned tabs.',
          'The Queue tab shows queries that are available to assign to yourself.',
          'The My Assigned tab shows queries you already own.',
          'Sort by urgency and status so urgent work is handled first.',
        ],
      },
      {
        title: 'Step 2: Take the case and review details',
        bullets: [
          'Open a query from Queue and press Assign to Me to take ownership.',
          'You must assign the query to yourself before you can respond to it.',
          'Read patient context, message history, and sources before deciding.',
        ],
      },
      {
        title: 'Step 3: Choose a review action',
        bullets: [
          'Use review actions to approve, request changes, or provide a manual response.',
          'When requesting changes, write short and clear instructions.',
        ],
      },
      {
        title: 'Step 4: Finish and update status',
        bullets: [
          'Refresh and check statuses so no active consultations are left unresolved.',
          'Add comments when needed so the GP gets clear next steps.',
        ],
      },
    ],
    features: [
      'Sort and filter by status, severity, specialty, and creation date.',
      'Review consultation and message-level controls from the specialist detail page.',
      'Attach additional files and source references when manual responses are needed.',
      'Track pending workload with queue and assignment indicators.',
    ],
    limitations: [
      'AI drafts can miss details, so always check them before approval.',
      'Use clear comments so GPs understand what to do next.',
      'Do not rely on claims that have no supporting source.',
      'Use your normal emergency and safety process for urgent risks.',
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
          <ol className="mt-4 space-y-4 text-gray-800 list-decimal list-inside">
            {content.steps.map((step) => (
              <li key={step.title} className="bg-slate-50 border border-slate-200 rounded-lg p-4">
                <h3 className="font-semibold text-gray-900">{step.title}</h3>
                <ul className="mt-2 space-y-2 text-gray-800 list-disc list-inside">
                  {step.bullets.map((bullet) => (
                    <li key={bullet}>{bullet}</li>
                  ))}
                </ul>
              </li>
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
