import {act, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Route, useLocation} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import {api} from '../lib/api';
import {Protected} from '../lib/auth';
import {returnPath, signInHref} from '../lib/sign-in';
import {AppShell} from '../components/app-shell';
import type {AuthSession} from '../lib/types';
import {LoginPage} from '../pages/candidate';
import {HRDashboardPage} from '../pages/hr';
import {candidateUser, hrUser, session} from './fixtures';
import {deferred, mockApi, renderRoutes} from './helpers';

beforeEach(mockApi);

function LoginDestination() {const location = useLocation(); return <p>{location.pathname} · requested {location.state?.from}</p>;}

describe('authentication and role boundaries', () => {
  it('redirects an anonymous application request to candidate login with its original destination', async () => {
    vi.mocked(api.session).mockResolvedValue(session(null));
    renderRoutes(<><Route path="/jobs/:id/apply" element={<Protected role="candidate"><p>Private application form</p></Protected>} /><Route path="/login" element={<LoginDestination />} /></>, '/jobs/TEST-ENG-001/apply');
    expect(await screen.findByText('/login · requested /jobs/TEST-ENG-001/apply')).toBeVisible();
    expect(screen.queryByText('Private application form')).not.toBeInTheDocument();
  });

  it('keeps a candidate out of the HR workspace and does not fetch HR data', async () => {
    vi.mocked(api.session).mockResolvedValue(session(candidateUser));
    renderRoutes(<><Route path="/hr" element={<Protected role="hr"><HRDashboardPage /></Protected>} /><Route path="/hr/login" element={<LoginDestination />} /></>, '/hr');
    expect(await screen.findByText('/hr/login · requested /hr')).toBeVisible();
    expect(api.jobs).not.toHaveBeenCalled();
    expect(api.candidates).not.toHaveBeenCalled();
  });

  it('carries the complete selected application URL into the external LinkedIn sign-in', async () => {
    vi.mocked(api.session).mockResolvedValue(session(null));
    const target = '/jobs/TEST-ENG-001/apply?source=job-post#contact';
    renderRoutes(<><Route path="/jobs/:id/apply" element={<Protected role="candidate"><p>Private application form</p></Protected>} /><Route path="/login" element={<LoginPage />} /></>, target);
    expect(await screen.findByRole('link', {name: 'Continue with LinkedIn'})).toHaveAttribute('href', '/auth/linkedin/login?return_to=' + encodeURIComponent(target));
  });

  it('keeps the current JD as the destination when using the global sign-in button', async () => {
    vi.mocked(api.session).mockResolvedValue(session(null));
    const target = '/jobs/TEST-ENG-001?source=campaign#requirements';
    renderRoutes(<Route element={<AppShell />}><Route path="/jobs/:id" element={<p>Selected job description</p>} /><Route path="/login" element={<LoginPage />} /></Route>, target);
    await userEvent.click(await screen.findByRole('link', {name: 'Sign in'}));
    expect(screen.getByRole('link', {name: 'Continue with LinkedIn'})).toHaveAttribute('href', '/auth/linkedin/login?return_to=' + encodeURIComponent(target));
  });

  it('returns demo sign-in to the selected application instead of the application list', async () => {
    vi.mocked(api.session).mockResolvedValue(session(null));
    vi.spyOn(api, 'demoLogin').mockResolvedValue(session(candidateUser));
    renderRoutes(<><Route path="/jobs/:id/apply" element={<Protected role="candidate"><p>Selected role application form</p></Protected>} /><Route path="/login" element={<LoginPage />} /></>, '/jobs/TEST-ENG-001/apply');
    await userEvent.click(await screen.findByRole('button', {name: 'Explore candidate demo'}));
    expect(await screen.findByText('Selected role application form')).toBeVisible();
  });

  it('does not admit an HR session to candidate-only application pages', async () => {
    vi.mocked(api.session).mockResolvedValue(session(hrUser));
    renderRoutes(<><Route path="/candidate/applications" element={<Protected role="candidate"><p>Candidate applications</p></Protected>} /><Route path="/login" element={<LoginDestination />} /></>, '/candidate/applications');
    expect(await screen.findByText('/login · requested /candidate/applications')).toBeVisible();
    expect(screen.queryByText('Candidate applications')).not.toBeInTheDocument();
  });

  it('waits for identity verification before rendering confidential HR content', async () => {
    const request = deferred<AuthSession>();
    vi.mocked(api.session).mockReturnValueOnce(request.promise);
    renderRoutes(<Route path="/hr" element={<Protected role="hr"><h1>Confidential candidate evidence</h1></Protected>} />, '/hr');
    expect(screen.getByRole('status', {name: 'Loading'})).toBeVisible();
    expect(screen.queryByRole('heading')).not.toBeInTheDocument();
    await act(async () => request.resolve(session(hrUser)));
    expect(await screen.findByRole('heading', {name: 'Confidential candidate evidence'})).toBeVisible();
  });

  it('provides a retry when session verification fails instead of treating failure as permission', async () => {
    vi.mocked(api.session).mockRejectedValueOnce(new Error('Identity service unavailable')).mockResolvedValueOnce(session(hrUser));
    renderRoutes(<Route path="/hr" element={<Protected role="hr"><h1>Verified HR workspace</h1></Protected>} />, '/hr');
    expect(await screen.findByRole('alert')).toHaveTextContent('Identity service unavailable');
    expect(screen.queryByText('Verified HR workspace')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', {name: 'Try again'}));
    expect(await screen.findByRole('heading', {name: 'Verified HR workspace'})).toBeVisible();
  });

  it('signs in with HR credentials and returns to the requested protected page', async () => {
    vi.mocked(api.session).mockResolvedValue(session(null));
    const login = vi.spyOn(api, 'hrLogin').mockResolvedValue(session(hrUser));
    renderRoutes(<><Route path="/hr/login" element={<LoginPage hr />} /><Route path="/hr/jobs/TEST/candidates" element={<Protected role="hr"><p>Requested HR candidates</p></Protected>} /></>, '/hr/jobs/TEST/candidates');
    const username = await screen.findByRole('textbox', {name: 'Username'});
    await userEvent.type(username, 'fixture@staff');
    await userEvent.type(screen.getByLabelText('Password'), 'test-only-password');
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');
    expect(screen.queryByRole('link', {name: 'Sign in with Microsoft'})).not.toBeInTheDocument();
    expect(screen.queryByRole('button', {name: 'Explore HR demo'})).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', {name: 'Sign in to HR'}));
    expect(login).toHaveBeenCalledWith('fixture@staff', 'test-only-password');
    expect(await screen.findByText('Requested HR candidates')).toBeVisible();
  });

  it('shows rejected HR credentials without rendering protected data', async () => {
    vi.mocked(api.session).mockResolvedValue({...session(null), demo_mode: false});
    vi.spyOn(api, 'hrLogin').mockRejectedValue(new Error('Invalid username or password'));
    renderRoutes(<><Route path="/hr/login" element={<LoginPage hr />} /><Route path="/hr" element={<Protected role="hr"><p>Confidential HR data</p></Protected>} /></>, '/hr/login');
    await userEvent.type(await screen.findByRole('textbox', {name: 'Username'}), 'wrong@staff');
    await userEvent.type(screen.getByLabelText('Password'), 'wrong-test-password');
    await userEvent.click(screen.getByRole('button', {name: 'Sign in to HR'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid username or password');
    expect(screen.queryByText('Confidential HR data')).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Sign in to HR'})).toBeEnabled();
  });

  it('hides demo authentication in production mode', async () => {
    vi.mocked(api.session).mockResolvedValue({...session(null), demo_mode: false});
    renderRoutes(<Route path="/login" element={<LoginPage />} />, '/login');
    expect(screen.getByRole('link', {name: 'Continue with LinkedIn'})).toHaveAttribute('href', '/auth/linkedin/login');
    await waitFor(() => expect(screen.queryByText('Checking workspace…')).not.toBeInTheDocument());
    expect(screen.queryByRole('button', {name: 'Explore candidate demo'})).not.toBeInTheDocument();
  });
});

describe('sign-in destinations', () => {
  it.each([
    'https://external.example/jobs/TEST/apply',
    '//external.example/jobs/TEST/apply',
    '/jobs/TEST\\external',
    '/jobs/%2e%2e/hr',
    '/jobs/../hr',
    '/login',
    '/hr/jobs',
  ])('does not send an unsafe or unrelated candidate destination: %s', (target) => {
    expect(returnPath(target)).toBeNull();
    expect(signInHref(false, target)).toBe('/auth/linkedin/login');
  });

  it('preserves an encoded requirement identifier and supports protected HR destinations', () => {
    expect(returnPath('/jobs/REQ%20ENG/apply?source=post#contact')).toBe('/jobs/REQ%20ENG/apply?source=post#contact');
    expect(signInHref(true, '/hr/jobs/TEST/candidates/APP')).toBe('/auth/hr/login?return_to=%2Fhr%2Fjobs%2FTEST%2Fcandidates%2FAPP');
  });
});
