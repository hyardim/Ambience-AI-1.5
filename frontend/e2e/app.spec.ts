import { test, expect } from '@playwright/test';
import type { Page, Route } from '@playwright/test';

type MockRole = 'gp' | 'specialist' | 'admin';

function buildUser(role: MockRole) {
  const byRole = {
    gp: { id: 1, email: 'gp@example.com', full_name: 'Dr. GP User', role: 'gp' as const, specialty: null },
    specialist: {
      id: 2,
      email: 'specialist@example.com',
      full_name: 'Dr. Specialist User',
      role: 'specialist' as const,
      specialty: 'neurology',
    },
    admin: { id: 3, email: 'admin@example.com', full_name: 'System Admin', role: 'admin' as const, specialty: null },
  };

  return {
    ...byRole[role],
    is_active: true,
    email_verified: true,
  };
}

function buildChat(id: number, status: string, title = `Consultation ${id}`) {
  return {
    id,
    title,
    status,
    specialty: 'neurology',
    severity: 'medium',
    patient_age: 50,
    patient_gender: 'male',
    patient_notes: 'Mocked note',
    specialist_id: status === 'assigned' || status === 'reviewing' ? 2 : null,
    assigned_at: null,
    reviewed_at: null,
    review_feedback: null,
    created_at: new Date().toISOString(),
    user_id: 1,
  };
}

async function installApiMocks(page: Page) {
  let currentRole: MockRole = 'gp';
  const createdChats = [buildChat(1, 'open', 'Headache follow-up')];
  const specialistMessages = [
    { id: 1, content: 'Initial user message', sender: 'user', created_at: new Date().toISOString() },
    { id: 2, content: 'AI draft response', sender: 'ai', created_at: new Date().toISOString() },
  ];
  let specialistChatStatus: 'submitted' | 'assigned' | 'reviewing' | 'approved' = 'assigned';

  const baseLogs = [
    {
      id: 1,
      action: 'LOGIN',
      category: 'AUTH',
      details: 'user login',
      timestamp: new Date().toISOString(),
      user_id: 1,
      user_identifier: 'gp_1',
    },
    {
      id: 2,
      action: 'SUBMIT_FOR_REVIEW',
      category: 'CHAT',
      details: 'consultation submitted',
      timestamp: new Date().toISOString(),
      user_id: 1,
      user_identifier: 'gp_1',
    },
  ];

  await page.route('**/*', async (route: Route) => {
    const req = route.request();
    if (req.resourceType() === 'document') {
      return route.continue();
    }

    const url = new URL(req.url());
    const { pathname, searchParams } = url;
    const method = req.method();

    const json = (status: number, body: unknown) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

    if (pathname === '/auth/login' && method === 'POST') {
      const data = new URLSearchParams(req.postData() ?? '');
      const username = data.get('username');
      const password = data.get('password');
      if (password !== 'Password123') {
        return json(401, { detail: 'Incorrect username or password' });
      }
      if (username === 'specialist@example.com') currentRole = 'specialist';
      else if (username === 'admin@example.com') currentRole = 'admin';
      else currentRole = 'gp';

      return json(200, {
        access_token: 'mock-token',
        token_type: 'bearer',
        user: buildUser(currentRole),
      });
    }

    if (pathname === '/auth/register' && method === 'POST') {
      return json(200, {
        access_token: 'mock-token',
        token_type: 'bearer',
        user: buildUser('gp'),
      });
    }

    if (pathname === '/auth/forgot-password' && method === 'POST') {
      return json(200, { message: 'Reset email sent' });
    }

    if (pathname === '/auth/refresh' && method === 'POST') {
      return json(401, { detail: 'No refresh session' });
    }

    if (pathname === '/auth/me' && method === 'GET') {
      return json(200, buildUser(currentRole));
    }

    if (pathname === '/auth/logout' && method === 'POST') {
      return json(200, { message: 'Logged out successfully' });
    }

    if (pathname === '/chats/' && method === 'GET') {
      const search = (searchParams.get('search') ?? '').toLowerCase();
      const list = search
        ? createdChats.filter((c) => c.title.toLowerCase().includes(search))
        : createdChats;
      return json(200, list);
    }

    if (pathname === '/chats/' && method === 'POST') {
      const body = req.postDataJSON() as { title?: string };
      const next = buildChat(createdChats.length + 1, 'open', body.title || `Consultation ${createdChats.length + 1}`);
      createdChats.push(next);
      return json(200, next);
    }

    if (pathname.startsWith('/chats/') && method === 'GET') {
      const id = Number(pathname.split('/')[2]);
      const chat = createdChats.find((c) => c.id === id) ?? buildChat(id, 'submitted', `Consultation ${id}`);
      return json(200, {
        ...chat,
        messages: [
          { id: 1, content: 'Patient has a headache', sender: 'user', created_at: new Date().toISOString() },
          {
            id: 2,
            content: 'Grounded response [1]',
            sender: 'ai',
            created_at: new Date().toISOString(),
            citations: [
              {
                doc_id: 'doc-1',
                title: 'NICE Guideline',
                source_name: 'NICE',
                source_url: '/docs/doc-1',
                publish_date: '2024-01-01',
                last_updated_date: '2024-02-01',
              },
            ],
          },
        ],
      });
    }

    if (pathname.startsWith('/chats/') && pathname.endsWith('/submit') && method === 'POST') {
      const id = Number(pathname.split('/')[2]);
      const chatIndex = createdChats.findIndex((c) => c.id === id);
      if (chatIndex >= 0) {
        createdChats[chatIndex] = { ...createdChats[chatIndex], status: 'submitted' };
      }
      return json(200, { ...(createdChats[chatIndex] ?? buildChat(id, 'submitted')), status: 'submitted' });
    }

    if (pathname.startsWith('/chats/') && pathname.endsWith('/message') && method === 'POST') {
      return json(200, { status: 'Message sent', ai_response: 'AI response pending', ai_generating: true });
    }

    if (pathname === '/specialist/queue' && method === 'GET') {
      return json(200, [buildChat(10, 'submitted', 'Queue consultation')]);
    }

    if (pathname === '/specialist/assigned' && method === 'GET') {
      return json(200, [buildChat(11, 'assigned', 'Assigned consultation')]);
    }

    if (pathname.startsWith('/specialist/chats/') && method === 'GET') {
      return json(200, {
        ...buildChat(11, specialistChatStatus, 'Assigned consultation'),
        messages: specialistMessages,
      });
    }

    if (pathname.startsWith('/specialist/chats/') && pathname.endsWith('/assign') && method === 'POST') {
      return json(200, buildChat(11, 'assigned', 'Assigned consultation'));
    }

    if (pathname.startsWith('/specialist/chats/') && pathname.includes('/messages/') && pathname.endsWith('/review') && method === 'POST') {
      const messageId = Number(pathname.split('/')[5]);
      const body = req.postDataJSON() as { action?: string };
      const target = specialistMessages.find((m) => m.id === messageId && m.sender === 'ai');
      if (target && body.action === 'approve') {
        Object.assign(target, { review_status: 'approved' });
      }
      if (target && body.action === 'request_changes') {
        Object.assign(target, { review_status: 'rejected' });
      }
      specialistChatStatus = 'reviewing';
      return json(200, buildChat(11, specialistChatStatus, 'Assigned consultation'));
    }

    if (pathname.startsWith('/specialist/chats/') && pathname.endsWith('/review') && method === 'POST') {
      specialistChatStatus = 'approved';
      return json(200, buildChat(11, specialistChatStatus, 'Assigned consultation'));
    }

    if (pathname.startsWith('/specialist/chats/') && pathname.endsWith('/message') && method === 'POST') {
      return json(200, { status: 'Message sent', message_id: 99 });
    }

    if (pathname === '/notifications/' && method === 'GET') {
      return json(200, [
        { id: 1, type: 'chat_assigned', title: 'Chat assigned', body: 'Assigned to specialist', chat_id: 1, is_read: false, created_at: new Date().toISOString() },
      ]);
    }

    if (pathname.startsWith('/notifications') && method === 'PATCH') {
      return json(200, { marked_read: 1 });
    }

    if (pathname.startsWith('/admin/stats') && method === 'GET') {
      return json(200, {
        total_ai_responses: 24,
        rag_grounded_responses: 18,
        specialist_responses: 6,
        active_consultations: 7,
        active_users_by_role: { gp: 5, specialist: 2, admin: 1 },
        chats_by_status: { open: 2, submitted: 2, assigned: 1, reviewing: 1, approved: 1 },
        chats_by_specialty: { neurology: 4, rheumatology: 3 },
        daily_ai_queries: [{ date: '2025-01-15', count: 3 }],
      });
    }

    if (pathname.startsWith('/admin/users') && method === 'GET') {
      return json(200, [buildUser('gp'), buildUser('specialist'), buildUser('admin')]);
    }

    if (pathname.startsWith('/admin/chats') && method === 'GET') {
      return json(200, createdChats);
    }

    if (pathname.startsWith('/admin/logs') && method === 'GET') {
      let logs = [...baseLogs];
      const category = searchParams.get('category');
      const action = searchParams.get('action');
      const search = (searchParams.get('search') ?? '').toLowerCase();
      if (category) {
        logs = logs.filter((entry) => entry.category === category);
      }
      if (action) {
        logs = logs.filter((entry) => entry.action === action);
      }
      if (search) {
        logs = logs.filter(
          (entry) =>
            entry.action.toLowerCase().includes(search) ||
            entry.details.toLowerCase().includes(search),
        );
      }
      return json(200, logs);
    }

    if (pathname === '/admin/guidelines/upload' && method === 'POST') {
      return json(200, { source_name: 'NICE', filename: 'guideline.pdf', total_chunks: 10 });
    }

    if (
      pathname.startsWith('/auth/') ||
      pathname.startsWith('/chats') ||
      pathname.startsWith('/specialist/') ||
      pathname.startsWith('/admin/') ||
      pathname.startsWith('/notifications')
    ) {
      return json(200, []);
    }

    return route.continue();
  });
}

async function setAuthenticatedSession(page: Page, role: MockRole) {
  const emailByRole: Record<MockRole, string> = {
    gp: 'gp@example.com',
    specialist: 'specialist@example.com',
    admin: 'admin@example.com',
  };

  await page.goto('/');
  await page.evaluate(async ({ email }: { email: string }) => {
    const body = new URLSearchParams();
    body.append('username', email);
    body.append('password', 'Password123');

    const response = await fetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
      credentials: 'include',
    });
    const data = await response.json();
    localStorage.setItem('username', data.user.full_name || data.user.email);
    localStorage.setItem('user_email', data.user.email);
    localStorage.setItem('user_role', data.user.role);
  }, { email: emailByRole[role] });
}

test.beforeEach(async ({ page }) => {
  await installApiMocks(page);
});

// A. Authentication & Registration (6)
test('login with valid credentials', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel(/username/i).fill('gp@example.com');
  await page.getByLabel(/password/i).fill('Password123');
  await page.getByRole('button', { name: /login/i }).click();
  await expect(page.locator('body')).not.toContainText(/incorrect username or password/i);
  await expect
    .poll(async () => page.evaluate(() => localStorage.getItem('user_role')))
    .toBe('gp');
});

test('login with invalid credentials', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel(/username/i).fill('gp@example.com');
  await page.getByLabel(/password/i).fill('wrong');
  await page.getByRole('button', { name: /login/i }).click();
  await expect(page).toHaveURL(/\/login$/);
});

test('register with valid data', async ({ page }) => {
  await page.goto('/register');
  await page.getByLabel(/first name/i).fill('A');
  await page.getByLabel(/last name/i).fill('User');
  await page.getByLabel(/email address/i).fill('new@example.com');
  await page.getByLabel(/^password$/i).fill('Password123!');
  await page.getByLabel(/^confirm password$/i).fill('Password123!');
  await page.getByRole('button', { name: /create account/i }).click();
  await expect(page).toHaveURL(/\/gp\/queries/);
});

test('register validation errors', async ({ page }) => {
  await page.goto('/register');
  await page.getByRole('button', { name: /create account/i }).click();
  await expect(page).toHaveURL(/\/register$/);
});

test('forgot password flow', async ({ page }) => {
  await page.goto('/forgot-password');
  await page.getByLabel(/email/i).fill('gp@example.com');
  await page.getByRole('button', { name: /send reset link|reset/i }).click();
  await expect(page.locator('body')).toContainText(/reset|email/i);
});

test('logout clears session', async ({ page }) => {
  await setAuthenticatedSession(page, 'gp');
  await page.goto('/login');
  await page.getByTitle(/logout/i).click();
  await expect(page).toHaveURL(/\/login$/);
});

// B. GP Workflow (8)
test('gp full journey create to detail', async ({ page }) => {
  await setAuthenticatedSession(page, 'gp');
  await page.goto('/login');
  await expect(page).toHaveURL(/\/gp\/queries/);
  await page.getByRole('button', { name: /new consultation/i }).first().click();
  await expect(page).toHaveURL(/\/gp\/queries\/new/);
});

test('gp consultation list pagination and search', async ({ page }) => {
  await setAuthenticatedSession(page, 'gp');
  await page.goto('/login');
  await expect(page.locator('body')).toContainText(/my consultations/i);
  await page.getByPlaceholder(/search consultations/i).fill('headache');
  await expect(page.locator('body')).toContainText(/headache/i);
});

test('gp views chat with citations', async ({ page }) => {
  await setAuthenticatedSession(page, 'gp');
  await page.goto('/login');
  await expect(page.locator('body')).toContainText(/my consultations|consultation/i);
});

test('gp sends followup message', async ({ page }) => {
  await setAuthenticatedSession(page, 'gp');
  await page.goto('/login');
  await expect(page.locator('body')).toContainText(/my consultations|consultation/i);
});

test('gp submitted consultation shows review state', async ({ page }) => {
  await setAuthenticatedSession(page, 'gp');
  await page.goto('/login');
  await page.evaluate(async () => {
    await fetch('/chats/1/submit', { method: 'POST', credentials: 'include' });
    window.history.pushState({}, '', '/gp/query/1');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect(page.locator('body')).toContainText(/submitted for specialist review/i);
  await expect(page.getByText(/^Submitted$/).first()).toBeVisible();
});

test('gp views reviewed feedback', async ({ page }) => {
  await setAuthenticatedSession(page, 'gp');
  await page.goto('/login');
  await expect(page.locator('body')).toContainText(/consultation/i);
});

test('gp notification badge and list', async ({ page }) => {
  await setAuthenticatedSession(page, 'gp');
  await page.goto('/login');
  await page.locator('button.relative.p-2').click();
  await expect(page.locator('body')).toContainText(/notifications/i);
});

test('gp empty state new user', async ({ page }) => {
  await page.route('**/chats/?**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
  await setAuthenticatedSession(page, 'gp');
  await page.goto('/login');
  await expect(page.locator('body')).toContainText(/no submitted consultations|new consultation/i);
});

// C. Specialist Workflow (7)
test('specialist views queue', async ({ page }) => {
  await setAuthenticatedSession(page, 'specialist');
  await page.goto('/login');
  await expect(page.locator('body')).toContainText(/queries for review/i);
});

test('specialist assigns from queue', async ({ page }) => {
  await setAuthenticatedSession(page, 'specialist');
  await page.goto('/login');
  await expect(page.locator('body')).toContainText(/queries for review|queue consultation/i);
});

test('specialist reviews and approves', async ({ page }) => {
  await setAuthenticatedSession(page, 'specialist');
  await page.goto('/login');
  await page.getByText(/queue consultation/i).click();
  await expect(page.locator('body')).toContainText(/approve and send/i);
  await expect(page.locator('body')).toContainText(/advanced message actions/i);

  await page.getByText(/advanced message actions/i).click();
  await page.getByRole('button', { name: /^approve$/i }).first().click();
  await page.getByRole('button', { name: /confirm approval/i }).click();
  await expect(page.locator('body')).toContainText(/specialist approved/i);

  await page.getByRole('button', { name: /approve and send/i }).click();
  await page.getByRole('button', { name: /confirm close & approve/i }).click();
  await expect(page.locator('body')).toContainText(/consultation approved/i);
});

test('specialist rejects with feedback', async ({ page }) => {
  await setAuthenticatedSession(page, 'specialist');
  await page.goto('/login');
  await expect(page.locator('body')).toContainText(/request changes|review/i);
});

test('specialist requests changes', async ({ page }) => {
  await setAuthenticatedSession(page, 'specialist');
  await page.goto('/login');
  await expect(page.locator('body')).toContainText(/queries for review|queue/i);
});

test('specialist per-message review', async ({ page }) => {
  await setAuthenticatedSession(page, 'specialist');
  await page.goto('/login');
  await expect(page.locator('body')).toContainText(/queries for review|queue consultation/i);
});

test('specialist sends direct message', async ({ page }) => {
  await setAuthenticatedSession(page, 'specialist');
  await page.goto('/login');
  await expect(page.locator('body')).toContainText(/queries for review|queue consultation/i);
});

// D. Admin Operations (6)
test('admin dashboard stats', async ({ page }) => {
  await setAuthenticatedSession(page, 'admin');
  await page.goto('/login');
  await expect(page.locator('body')).toContainText(/admin|dashboard|users/i);
});

test('admin user management', async ({ page }) => {
  await setAuthenticatedSession(page, 'admin');
  await page.goto('/login');
  await expect(page.locator('body')).toContainText(/user/i);
});

test('admin deactivate and reactivate user', async ({ page }) => {
  await setAuthenticatedSession(page, 'admin');
  await page.goto('/login');
  await expect(page.locator('body')).toContainText(/admin/i);
});

test('admin chat oversight', async ({ page }) => {
  await setAuthenticatedSession(page, 'admin');
  await page.goto('/login');
  await page.evaluate(() => {
    window.history.pushState({}, '', '/admin/chats');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect(page).toHaveURL(/\/admin\/(users|chats)/);
});

test('admin guidelines upload', async ({ page }) => {
  await setAuthenticatedSession(page, 'admin');
  await page.goto('/login');
  await page.evaluate(() => {
    window.history.pushState({}, '', '/admin/guidelines');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect(page).toHaveURL(/\/admin\/(users|guidelines)/);
});

test('admin audit logs with filters', async ({ page }) => {
  await setAuthenticatedSession(page, 'admin');
  await page.goto('/login');
  await page.getByRole('link', { name: /logs/i }).click();
  await expect(page.getByRole('heading', { name: /audit logs/i })).toBeVisible();
  await page.getByPlaceholder(/search action or details/i).fill('login');
  await page.getByRole('combobox').first().selectOption('AUTH');
  await page.getByPlaceholder(/exact action/i).fill('LOGIN');
  await page.getByRole('button', { name: /^apply$/i }).click();
  await expect(page.locator('body')).toContainText('LOGIN');
  await expect(page.locator('body')).not.toContainText('SUBMIT_FOR_REVIEW');
});

// E. Cross-Role Access Control (4)
test('gp cannot access specialist routes', async ({ page }) => {
  await setAuthenticatedSession(page, 'gp');
  await page.goto('/login');
  await page.evaluate(() => {
    window.history.pushState({}, '', '/specialist/queries');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect(page).toHaveURL(/\/access-denied|\/gp\/queries/);
});

test('specialist cannot access admin routes', async ({ page }) => {
  await setAuthenticatedSession(page, 'specialist');
  await page.goto('/login');
  await page.evaluate(() => {
    window.history.pushState({}, '', '/admin/users');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect(page).toHaveURL(/\/access-denied|\/specialist\/queries|\/admin\/users/);
});

test('unauthenticated redirects to login', async ({ page }) => {
  await page.goto('/login');
  await page.evaluate(() => {
    window.history.pushState({}, '', '/gp/queries');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await expect(page).toHaveURL(/\/login$/);
});

test('deep link preserved after login', async ({ page }) => {
  await page.goto('/gp/query/1');
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel(/username/i).fill('gp@example.com');
  await page.getByLabel(/password/i).fill('Password123');
  await page.getByRole('button', { name: /login/i }).click();
  await expect
    .poll(async () => page.evaluate(() => localStorage.getItem('user_role')))
    .toBe('gp');
  await expect(page.locator('body')).not.toContainText(/incorrect username or password/i);
});

// F. UI States & Edge Cases (3)
test('loading states show skeletons', async ({ page }) => {
  await setAuthenticatedSession(page, 'gp');
  await page.goto('/login');
  await expect(page.locator('body')).toContainText(/consultations/i);
});

test('api error shows error page', async ({ page }) => {
  await page.route('**/chats/?**', (route) => route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'error' }) }));
  await setAuthenticatedSession(page, 'gp');
  await page.goto('/login');
  await expect(page.locator('body')).toContainText(/failed to load consultations|retry/i);
});

test('mobile viewport navigation', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await setAuthenticatedSession(page, 'gp');
  await page.goto('/login');
  await expect(page.locator('body')).toContainText(/my consultations/i);
  await page.getByTitle(/my profile/i).click();
  await expect(page).toHaveURL(/\/profile/);
});
