import {act, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {Route, useLocation} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import {api} from '../lib/api';
import {Protected} from '../lib/auth';
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

  it('labels demo access separately from external authentication and sends the selected HR role', async () => {
    vi.mocked(api.session).mockResolvedValue(session(null));
    const demo = vi.spyOn(api, 'demoLogin').mockResolvedValue(session(hrUser));
    renderRoutes(<><Route path="/hr/login" element={<LoginPage hr />} /><Route path="/hr" element={<Protected role="hr"><p>Signed in to HR demo</p></Protected>} /></>, '/hr/login');
    expect(await screen.findByRole('button', {name: 'Explore HR demo'})).toBeVisible();
    expect(screen.getByRole('link', {name: 'Sign in with Microsoft'})).toHaveAttribute('href', '/auth/hr/login');
    expect(screen.getByText(/fictional jobs and candidate evidence/)).toBeVisible();
    await userEvent.click(screen.getByRole('button', {name: 'Explore HR demo'}));
    expect(demo).toHaveBeenCalledWith('hr');
    expect(await screen.findByText('Signed in to HR demo')).toBeVisible();
  });

  it('hides demo authentication in production mode', async () => {
    vi.mocked(api.session).mockResolvedValue({...session(null), demo_mode: false});
    renderRoutes(<Route path="/login" element={<LoginPage />} />, '/login');
    expect(screen.getByRole('link', {name: 'Continue with LinkedIn'})).toHaveAttribute('href', '/auth/linkedin/login');
    await waitFor(() => expect(screen.queryByText('Checking workspace…')).not.toBeInTheDocument());
    expect(screen.queryByRole('button', {name: 'Explore candidate demo'})).not.toBeInTheDocument();
  });
});
