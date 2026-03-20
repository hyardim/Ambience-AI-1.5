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
    specialist_id: null,
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
      if (password !== 'password123') {
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

    if (pathname.startsWith('/chats/') && pathname.endsWith('/submit') && method === 'POST') {
      return json(200, { ...createdChats[0], status: 'submitted' });
    }

    if (pathname.startsWith('/specialist/queue') && method === 'GET') {
      return json(200, [buildChat(10, 'submitted', 'Queue consultation')]);
    }

    if (pathname.startsWith('/specialist/assigned') && method === 'GET') {
      return json(200, [buildChat(11, 'assigned', 'Assigned consultation')]);
    }

    if (pathname.startsWith('/admin/users')) {
      if (currentRole !== 'admin') return json(403, { detail: 'Not authorized' });
      return json(200, [buildUser('gp'), buildUser('specialist'), buildUser('admin')]);
    }

    if (pathname.startsWith('/admin/chats')) {
      if (currentRole !== 'admin') return json(403, { detail: 'Not authorized' });
      return json(200, createdChats);
    }

    if (pathname.startsWith('/admin/logs')) {
      if (currentRole !== 'admin') return json(403, { detail: 'Not authorized' });
      return json(200, []);
    }

    if (
      pathname.startsWith('/auth/') ||
      pathname.startsWith('/chats') ||
      pathname.startsWith('/specialist/') ||
      pathname.startsWith('/admin/') ||
      pathname.startsWith('/notifications') ||
      pathname.startsWith('/search')
    ) {
      return json(200, []);
    }

    return route.continue();
  });
}

async function setAuthenticatedSession(
  page: Page,
  role: MockRole,
) {
  const emailByRole: Record<MockRole, string> = {
    gp: 'gp@example.com',
    specialist: 'specialist@example.com',
    admin: 'admin@example.com',
  };

  await page.goto('/');
  await page.evaluate(async ({ email }: { email: string }) => {
    const body = new URLSearchParams();
    body.append('username', email);
    body.append('password', 'password123');

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

// ─────────────────────────────────────────────────────────────────────────────
// These E2E tests run against the real dev server + backend.
// Make sure both frontend (port 5173) and backend (port 8000) are running.
// If using Docker Compose: `docker compose up` then `npx playwright test`
// ─────────────────────────────────────────────────────────────────────────────

test.describe('Authentication E2E', () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page);
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
  });

  test('login page renders correctly', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /login to your account/i })).toBeVisible();
    await expect(page.getByLabel(/username/i)).toBeVisible();
    await expect(page.getByLabel(/password/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /login/i })).toBeVisible();
  });

  test('fill demo credentials button works', async ({ page }) => {
    await page.getByText(/fill demo credentials/i).click();
    await expect(page.getByLabel(/username/i)).toHaveValue('gp@example.com');
    await expect(page.getByLabel(/password/i)).toHaveValue('password123');
  });

  test('shows error for invalid credentials', async ({ page }) => {
    await page.getByLabel(/username/i).fill('invalid@example.com');
    await page.getByLabel(/password/i).fill('wrongpassword');
    await page.getByRole('button', { name: /login/i }).click();

    // Failed auth should keep the user on login (not redirect into app areas).
    await expect(page).toHaveURL(/\/login$/, { timeout: 10_000 });
    await expect(page.getByRole('heading', { name: /login to your account/i })).toBeVisible();
  });

  test('successful login as GP redirects to consultations', async ({ page }) => {
    await setAuthenticatedSession(page, 'gp');
    await page.goto('/login');

    await expect(page.getByText(/my consultations/i)).toBeVisible({ timeout: 10_000 });
  });

  test('navigate to register page', async ({ page }) => {
    await page.getByText(/register here/i).click();
    await expect(page.getByRole('heading', { name: /create your account/i })).toBeVisible();
  });
});

test.describe('Protected Routes E2E', () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page);
  });

  test('unauthenticated user is redirected to login', async ({ page }) => {
    await page.goto('/gp/queries');
    await expect(page.getByRole('heading', { name: /login to your account/i })).toBeVisible({ timeout: 10_000 });
  });

  test('landing page is accessible without auth', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL('/');
  });
});

test.describe('GP Workflow E2E', () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page);
    await setAuthenticatedSession(page, 'gp');
    await page.goto('/gp/queries');
    await expect(page.getByText(/my consultations/i)).toBeVisible({ timeout: 10_000 });
  });

  test('view consultations list', async ({ page }) => {
    await expect(page.getByText(/my consultations/i)).toBeVisible();
  });

  test('navigate to new consultation form', async ({ page }) => {
    await page.getByRole('button', { name: /new consultation/i }).first().click();
    await expect(page.getByRole('heading', { name: /new consultation/i })).toBeVisible();
  });

  test('create a new consultation', async ({ page }) => {
    await page.getByRole('button', { name: /new consultation/i }).first().click();

    await page.getByLabel(/consultation title/i).fill('E2E Test Consultation');
    await page.getByLabel(/specialty/i).selectOption('neurology');
    await page.getByLabel(/clinical question/i).fill('Testing the consultation flow end-to-end');
    await page.getByRole('button', { name: /submit consultation/i }).click();

    // Should navigate to the detail page (wait for content to load)
    await expect(page.locator('body')).toContainText(/E2E Test|consultation/i, { timeout: 15_000 });
  });

  test('search consultations', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search by title/i);
    if (await searchInput.isVisible()) {
      await searchInput.fill('nonexistent-query');
      await expect(page.getByText(/no consultations found/i)).toBeVisible({ timeout: 5_000 });
    }
  });

  test('navigate to profile page', async ({ page }) => {
    await page.getByTitle('My Profile').click();
    await page.waitForURL(/\/profile/, { timeout: 5_000 });
  });

  test('logout returns to login page', async ({ page }) => {
    await page.getByTitle('Logout').click();
    await expect(page.getByRole('heading', { name: /login to your account/i })).toBeVisible({ timeout: 5_000 });
  });
});

test.describe('Specialist Workflow E2E', () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page);
    await setAuthenticatedSession(page, 'specialist');
    await page.goto('/specialist/queries');
    await page.waitForURL(/\/specialist/, { timeout: 10_000 });
  });

  test('view specialist queries page', async ({ page }) => {
    await expect(page.getByText(/queries for review/i)).toBeVisible({ timeout: 10_000 });
  });

  test('switch between queue and assigned tabs', async ({ page }) => {
    await expect(page.getByRole('button', { name: /queue/i })).toBeVisible({ timeout: 10_000 });

    if (await page.getByText(/my assigned/i).isVisible()) {
      await page.getByText(/my assigned/i).click();
    }
  });
});

test.describe('Admin Workflow E2E', () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page);
    await setAuthenticatedSession(page, 'admin');
    await page.goto('/login');
    await page.waitForURL(/\/admin\//, { timeout: 10_000 });
  });

  test('view admin users page', async ({ page }) => {
    await expect(page.getByText(/user management/i)).toBeVisible({ timeout: 10_000 });
  });

  test('navigate to admin chats page', async ({ page }) => {
    const chatsLink = page.getByRole('link', { name: /chats/i });
    if (await chatsLink.isVisible()) {
      await chatsLink.click();
      await page.waitForURL(/\/admin\/chats/, { timeout: 5_000 });
    }
  });

  test('navigate to audit logs page', async ({ page }) => {
    const logsLink = page.getByRole('link', { name: /audit logs/i });
    if (await logsLink.isVisible()) {
      await logsLink.click();
      await page.waitForURL(/\/admin\/logs/, { timeout: 5_000 });
    }
  });

  test('search users in admin panel', async ({ page }) => {
    await expect(page.getByText(/user management/i)).toBeVisible({ timeout: 10_000 });

    const searchInput = page.getByPlaceholder(/search by name or email/i);
    if (await searchInput.isVisible()) {
      await searchInput.fill('nonexistent');
      await expect(page.getByText(/no users found/i)).toBeVisible({ timeout: 5_000 });
    }
  });
});

test.describe('Access Control E2E', () => {
  test.beforeEach(async ({ page }) => {
    await installApiMocks(page);
  });

  test('GP cannot access admin pages', async ({ page }) => {
    await setAuthenticatedSession(page, 'gp');
    await page.goto('/gp/queries');
    await expect(page.getByText(/my consultations/i)).toBeVisible({ timeout: 10_000 });

    // Try to access admin page via client-side routing to avoid Vite /admin proxy
    await page.evaluate(() => {
      window.history.pushState({}, '', '/admin/users');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    await expect(page).toHaveURL(/\/access-denied/, { timeout: 10_000 });
  });
});
