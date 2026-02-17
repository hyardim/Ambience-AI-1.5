import type { Query, Notification, User } from '../types';

export const mockUsers: User[] = [
  {
    id: 'gp-1',
    name: 'Dr. Sarah Johnson',
    email: 'sarah.johnson@nhs.net',
    role: 'gp',
  },
  {
    id: 'specialist-1',
    name: 'Dr. James Wilson',
    email: 'james.wilson@nhs.net',
    role: 'specialist',
  },
];

export const mockQueries: Query[] = [
  {
    id: 'query-1',
    title: 'Patient presenting with recurring migraines and visual disturbances',
    description: 'I have a patient who is experiencing recurring migraines with visual aura. The episodes have increased in frequency over the past 3 months. Patient is a 42-year-old female with no prior history of neurological conditions.',
    specialty: 'neurology',
    severity: 'high',
    status: 'active',
    createdAt: new Date('2026-02-03T10:30:00'),
    updatedAt: new Date('2026-02-03T15:30:00'),
    gpId: 'gp-1',
    gpName: 'Dr. Sarah Johnson',
    messages: [
      {
        id: 'msg-1',
        senderId: 'gp-1',
        senderName: 'Dr. Sarah Johnson',
        senderType: 'gp',
        content: 'I have a patient who is experiencing recurring migraines with visual aura. The episodes have increased in frequency over the past 3 months. She reports seeing zigzag lines before the headache starts. Is this a sign of migraine with aura, and should I be concerned about any underlying conditions?',
        timestamp: new Date('2026-02-03T10:30:00'),
        attachments: [
          {
            id: 'file-1',
            name: 'Patient Symptom History.pdf',
            size: '2.4MB',
            type: 'application/pdf',
          },
        ],
      },
      {
        id: 'msg-2',
        senderId: 'ai',
        senderName: 'NHS AI Assistant',
        senderType: 'ai',
        content: 'Based on the symptoms described, this presentation is consistent with migraine with typical aura. The visual symptoms (zigzag lines) are characteristic of the visual aura phase. However, given the increase in frequency, I recommend:\n\n1. Consider prophylactic treatment if attacks occur ≥4 days per month\n2. Review for potential triggers (stress, sleep, diet)\n3. Consider referral if red flags present or prophylaxis ineffective\n\nThe NICE guidelines recommend beta-blockers (propranolol) or topiramate as first-line prophylaxis options.',
        timestamp: new Date('2026-02-03T10:32:00'),
        guidelineReference: {
          title: 'NICE Guidelines - Headaches in over 12s',
          referenceNo: 'CG150',
          lastUpdated: '15/09/2024',
        },
      },
    ],
    attachments: [
      {
        id: 'file-1',
        name: 'Patient Symptom History.pdf',
        size: '2.4MB',
        type: 'application/pdf',
      },
    ],
    specialistReviewRequired: true,
  },
  {
    id: 'query-2',
    title: 'Joint pain and morning stiffness in elderly patient',
    description: 'Patient presenting with symmetrical joint pain affecting small joints of hands and feet with morning stiffness lasting over an hour.',
    specialty: 'rheumatology',
    severity: 'medium',
    status: 'resolved',
    createdAt: new Date('2026-02-02T09:15:00'),
    updatedAt: new Date('2026-02-02T14:45:00'),
    gpId: 'gp-1',
    gpName: 'Dr. Sarah Johnson',
    messages: [
      {
        id: 'msg-3',
        senderId: 'gp-1',
        senderName: 'Dr. Sarah Johnson',
        senderType: 'gp',
        content: 'I have a 58-year-old patient presenting with symmetrical joint pain affecting the small joints of hands and feet. Morning stiffness lasts over an hour. ESR and CRP are elevated. Should I suspect rheumatoid arthritis and what initial investigations should I order?',
        timestamp: new Date('2026-02-02T09:15:00'),
      },
      {
        id: 'msg-4',
        senderId: 'ai',
        senderName: 'NHS AI Assistant',
        senderType: 'ai',
        content: 'The presentation strongly suggests inflammatory arthritis, possibly rheumatoid arthritis (RA). Key features supporting this:\n\n• Symmetrical small joint involvement\n• Morning stiffness >60 minutes\n• Elevated inflammatory markers\n\nRecommended investigations:\n1. Rheumatoid Factor (RF)\n2. Anti-CCP antibodies\n3. X-rays of hands and feet\n4. Full blood count\n\nEarly referral to rheumatology is crucial - NICE recommends urgent referral if RA suspected, aiming to start treatment within 3 months of symptom onset.',
        timestamp: new Date('2026-02-02T09:18:00'),
        guidelineReference: {
          title: 'NICE Guidelines - Rheumatoid arthritis in adults',
          referenceNo: 'NG100',
          lastUpdated: '12/07/2024',
        },
      },
      {
        id: 'msg-5',
        senderId: 'specialist-1',
        senderName: 'Dr. James Wilson',
        senderType: 'specialist',
        content: 'The AI response is accurate. I would add that given the clinical picture, please refer urgently using the 2-week pathway. In the meantime, consider short-term NSAIDs for symptom relief if no contraindications. The early window for treatment is critical for preventing joint damage.',
        timestamp: new Date('2026-02-02T14:45:00'),
      },
    ],
  },
  {
    id: 'query-3',
    title: 'Tremor assessment in 65-year-old patient',
    description: 'Patient has developed resting tremor in right hand over past 6 months. Family concerned about Parkinson\'s disease.',
    specialty: 'neurology',
    severity: 'medium',
    status: 'active',
    createdAt: new Date('2026-02-03T11:00:00'),
    updatedAt: new Date('2026-02-03T11:05:00'),
    gpId: 'gp-1',
    gpName: 'Dr. Sarah Johnson',
    messages: [
      {
        id: 'msg-6',
        senderId: 'gp-1',
        senderName: 'Dr. Sarah Johnson',
        senderType: 'gp',
        content: 'A 65-year-old male patient has developed a resting tremor in his right hand over the past 6 months. The tremor is worse at rest and improves with voluntary movement. His family has noticed he seems slower in his movements. They are concerned about Parkinson\'s disease. What clinical features should I look for and when should I refer?',
        timestamp: new Date('2026-02-03T11:00:00'),
      },
      {
        id: 'msg-7',
        senderId: 'ai',
        senderName: 'NHS AI Assistant',
        senderType: 'ai',
        content: 'The features you describe are concerning for Parkinsonism. Key clinical features to assess:\n\n**Cardinal features of Parkinson\'s disease:**\n• Bradykinesia (slowness) - ESSENTIAL for diagnosis\n• Resting tremor (4-6 Hz, \"pill-rolling\")\n• Rigidity (lead-pipe or cogwheel)\n• Postural instability (later feature)\n\n**Supportive features:**\n• Unilateral onset\n• Progressive course\n• Reduced arm swing\n• Hypomimia (reduced facial expression)\n• Micrographia\n\n**Referral:** NICE recommends referral to a specialist with expertise in Parkinson\'s disease for all patients with suspected Parkinsonism. Do not delay referral to undertake investigations.',
        timestamp: new Date('2026-02-03T11:05:00'),
        guidelineReference: {
          title: 'NICE Guidelines - Parkinson\'s disease in adults',
          referenceNo: 'NG71',
          lastUpdated: '21/06/2024',
        },
      },
    ],
    specialistReviewRequired: true,
  },
];

export const mockGPNotifications: Notification[] = [
  {
    id: 'notif-1',
    queryId: 'query-1',
    queryTitle: 'Patient presenting with recurring migraines...',
    message: 'NHS AI Assistant responded to your query',
    senderName: 'NHS AI Assistant',
    senderType: 'ai',
    read: false,
    timestamp: new Date('2026-02-03T10:32:00'),
  },
  {
    id: 'notif-2',
    queryId: 'query-2',
    queryTitle: 'Joint pain and morning stiffness...',
    message: 'Dr. James Wilson reviewed and responded',
    senderName: 'Dr. James Wilson',
    senderType: 'specialist',
    read: true,
    timestamp: new Date('2026-02-02T14:45:00'),
  },
];

export const mockSpecialistNotifications: Notification[] = [
  {
    id: 'notif-3',
    queryId: 'query-1',
    queryTitle: 'Patient presenting with recurring migraines...',
    message: 'New query pending your review',
    senderName: 'Dr. Sarah Johnson',
    senderType: 'ai',
    read: false,
    timestamp: new Date('2026-02-03T10:32:00'),
  },
  {
    id: 'notif-4',
    queryId: 'query-3',
    queryTitle: 'Tremor assessment in 65-year-old patient',
    message: 'New query pending your review',
    senderName: 'Dr. Sarah Johnson',
    senderType: 'ai',
    read: false,
    timestamp: new Date('2026-02-03T11:05:00'),
  },
];
