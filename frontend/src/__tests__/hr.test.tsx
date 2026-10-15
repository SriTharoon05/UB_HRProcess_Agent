import {act, screen, waitFor, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import {api} from '../lib/api';
import type {Candidate, CandidateResponse} from '../lib/types';
import {CandidateDetailPage, CandidateRankingPage, HRDashboardPage, HRJobsPage} from '../pages/hr';
import {candidateResponse, designCandidate, designJob, engineeringJob, evaluation, highCandidate, hrUser, lowerCandidate, pendingCandidate, session} from './fixtures';
import {deferred, mockApi, renderPage} from './helpers';

beforeEach(() => {mockApi(); vi.mocked(api.session).mockResolvedValue(session(hrUser));});

describe('HR workspace', () => {
  it('aggregates fetched records across job-scoped candidate APIs and discloses the limited scope', async () => {
    vi.mocked(api.candidates).mockImplementation(async id => candidateResponse(id === engineeringJob.requirement_id ? [highCandidate, pendingCandidate] : [designCandidate]));
    renderPage(<HRDashboardPage />);
    await screen.findAllByText('Casey Designer');
    expect(api.jobs).toHaveBeenCalledWith(true);
    expect(api.candidates).toHaveBeenCalledWith(engineeringJob.requirement_id);
    expect(api.candidates).toHaveBeenCalledWith(designJob.requirement_id);
    const profilesMetric = screen.getByText('Profiles returned').parentElement!;
    expect(within(profilesMetric).getByText('3')).toBeVisible();
    const evidenceMetric = screen.getByText('Evidence evaluations').parentElement!;
    expect(within(evidenceMetric).getByText('2')).toBeVisible();
    expect(within(evidenceMetric).getByText('1 processing in these lists')).toBeVisible();
    expect(screen.getByText(/not organization-wide totals/)).toBeVisible();
    expect(screen.getByRole('combobox', {name: 'Evidence overview job'})).toHaveValue(engineeringJob.requirement_id);
    expect(screen.getByText('Average in 1 returned job profiles').parentElement).toHaveTextContent('86/100');
    await userEvent.selectOptions(screen.getByRole('combobox', {name: 'Evidence overview job'}), designJob.requirement_id);
    expect(screen.getByText('Average in 1 returned job profiles').parentElement).toHaveTextContent('95/100');
  });

  it('exposes candidate-source errors and recovers independently of the jobs list', async () => {
    vi.mocked(api.jobs).mockResolvedValue([engineeringJob]);
    vi.mocked(api.candidates).mockRejectedValueOnce(new Error('Candidate list unavailable')).mockResolvedValueOnce(candidateResponse([highCandidate]));
    renderPage(<HRDashboardPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Candidate list unavailable');
    expect(screen.getByRole('link', {name: 'Frontend Engineer'})).toBeVisible();
    await userEvent.click(screen.getByRole('button', {name: 'Try again'}));
    expect(await screen.findByRole('link', {name: 'Review Alex Sample'})).toBeVisible();
  });

  it('searches HR requirements by requirement ID and department with candidate links', async () => {
    const user = userEvent.setup();
    renderPage(<HRJobsPage />);
    await screen.findByRole('link', {name: 'Frontend Engineer'});
    await user.type(screen.getByRole('textbox', {name: 'Search job requirements'}), designJob.requirement_id);
    expect(screen.queryByRole('link', {name: 'Frontend Engineer'})).not.toBeInTheDocument();
    const row = screen.getByRole('row', {name: /Product Designer/});
    expect(within(row).getByRole('link', {name: 'View candidates'})).toHaveAttribute('href', `/hr/jobs/${designJob.requirement_id}/candidates`);
    await user.selectOptions(screen.getByRole('combobox', {name: 'Filter by department'}), 'Engineering');
    expect(screen.getByText('No requirements found')).toBeVisible();
    await user.click(screen.getByRole('button', {name: 'Clear filters'}));
    expect(screen.getByRole('link', {name: 'Frontend Engineer'})).toBeVisible();
  });
});

function renderRanking() {return renderPage(<CandidateRankingPage />, {path: `/hr/jobs/${engineeringJob.requirement_id}/candidates`, route: '/hr/jobs/:requirementId/candidates'});}

describe('job-scoped candidate ranking', () => {
  it('refreshes the selected job candidates when HR requests an update', async () => {
    renderRanking();
    const refresh = await screen.findByRole('button', {name: 'Refresh list'});
    await waitFor(() => expect(refresh).toBeEnabled());
    await userEvent.click(refresh);
    await waitFor(() => expect(api.candidates).toHaveBeenCalledTimes(2));
    expect(api.candidates).toHaveBeenLastCalledWith(engineeringJob.requirement_id);
  });

  it('fetches only the selected job and sorts scored profiles while keeping pending records last', async () => {
    vi.mocked(api.candidates).mockResolvedValue(candidateResponse([pendingCandidate, lowerCandidate, highCandidate]));
    renderRanking();
    await screen.findByRole('link', {name: 'Alex Sample'});
    expect(api.candidates).toHaveBeenCalledWith(engineeringJob.requirement_id);
    expect(api.candidates).not.toHaveBeenCalledWith(designJob.requirement_id);
    const table = screen.getByRole('table');
    let rows = within(table).getAllByRole('row').slice(1);
    expect(rows.map(row => within(row).getByRole('link', {name: /Alex Sample|Morgan Example|Jamie Fixture/}).textContent)).toEqual(['Alex Sample', 'Morgan Example', 'Jamie Fixture']);
    await userEvent.click(screen.getByRole('button', {name: 'Score: highest first'}));
    rows = within(table).getAllByRole('row').slice(1);
    expect(rows.map(row => within(row).getByRole('link', {name: /Alex Sample|Morgan Example|Jamie Fixture/}).textContent)).toEqual(['Morgan Example', 'Alex Sample', 'Jamie Fixture']);
    expect(screen.getByText(/Limited to 25 profiles per job/)).toBeVisible();
    expect(screen.getByText(/not hiring verdicts/)).toBeVisible();
  });

  it('combines candidate search with evidence-label and processing filters', async () => {
    const user = userEvent.setup();
    vi.mocked(api.candidates).mockResolvedValue(candidateResponse([highCandidate, lowerCandidate, pendingCandidate]));
    renderRanking(); await screen.findByRole('link', {name: 'Alex Sample'});
    await user.type(screen.getByRole('textbox', {name: 'Search candidates'}), 'morgan@example.test');
    await user.selectOptions(screen.getByRole('combobox', {name: 'Filter match label'}), 'Partial evidence');
    await user.selectOptions(screen.getByRole('combobox', {name: 'Filter AI status'}), 'completed');
    expect(screen.getByRole('link', {name: 'Morgan Example'})).toBeVisible();
    expect(screen.queryByRole('link', {name: 'Alex Sample'})).not.toBeInTheDocument();
    expect(screen.getByText('Showing 1 of 3 returned profiles')).toBeVisible();
    await user.selectOptions(screen.getByRole('combobox', {name: 'Filter AI status'}), 'queued');
    expect(screen.getByText('No profiles match these filters')).toBeVisible();
    await user.click(screen.getAllByRole('button', {name: 'Clear filters'})[0]);
    expect(screen.getByRole('link', {name: 'Alex Sample'})).toBeVisible();
    expect(screen.getByRole('link', {name: 'Jamie Fixture'})).toBeVisible();
  });

  it('handles loading, failed retrieval, and retry without displaying fabricated profiles', async () => {
    const request = deferred<CandidateResponse>();
    vi.mocked(api.candidates).mockReturnValueOnce(request.promise).mockResolvedValueOnce(candidateResponse([]));
    renderRanking();
    expect(screen.getByRole('status', {name: 'Loading'})).toBeVisible();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    await act(async () => request.reject(new Error('D365 candidate retrieval failed')));
    expect(await screen.findByRole('alert')).toHaveTextContent('D365 candidate retrieval failed');
    await userEvent.click(screen.getByRole('button', {name: 'Try again'}));
    expect(await screen.findByText('Your next conversation is on its way')).toBeVisible();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });
});

function renderDetail() {return renderPage(<CandidateDetailPage />, {path: `/hr/jobs/${engineeringJob.requirement_id}/candidates/${highCandidate.application_id}`, route: '/hr/jobs/:requirementId/candidates/:applicationId'});}

describe('candidate evidence review', () => {
  it('queues a failed evaluation only once and refreshes its current status', async () => {
    const failed = {...pendingCandidate, ai_status: 'Failed'};
    const request = deferred<{success: boolean; application_id: string; ai_status: string; message: string}>();
    vi.mocked(api.candidate).mockResolvedValueOnce(failed).mockResolvedValue({...failed, ai_status: 'Queued'});
    const retry = vi.spyOn(api, 'retryEvaluation').mockReturnValue(request.promise);
    renderDetail();
    await userEvent.click(await screen.findByRole('button', {name: 'Retry evaluation'}));
    expect(screen.getByRole('button', {name: 'Queueing…'})).toBeDisabled();
    expect(retry).toHaveBeenCalledExactlyOnceWith(engineeringJob.requirement_id, highCandidate.application_id);
    await act(async () => request.resolve({success: true, application_id: failed.application_id, ai_status: 'Queued', message: 'Evaluation queued'}));
    expect(await screen.findByText('The evidence is still coming together')).toBeVisible();
    expect(screen.queryByRole('button', {name: 'Retry evaluation'})).not.toBeInTheDocument();
    expect(screen.queryByRole('img', {name: /out of 100/})).not.toBeInTheDocument();
  });

  it('keeps retry available and shows a retry request failure to HR', async () => {
    vi.mocked(api.candidate).mockResolvedValue({...pendingCandidate, ai_status: 'Failed'});
    vi.spyOn(api, 'retryEvaluation').mockRejectedValue(new Error('Evaluation queue temporarily unavailable'));
    renderDetail();
    await userEvent.click(await screen.findByRole('button', {name: 'Retry evaluation'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Evaluation queue temporarily unavailable');
    expect(screen.getByRole('button', {name: 'Retry evaluation'})).toBeEnabled();
  });

  it('ties evaluation to both job and application and exposes source evidence, partial support, and gaps', async () => {
    const user = userEvent.setup();
    renderDetail();
    expect(await screen.findByRole('heading', {name: 'Alex Sample'})).toBeVisible();
    expect(api.candidate).toHaveBeenCalledWith(engineeringJob.requirement_id, highCandidate.application_id);
    expect(screen.getByRole('img', {name: '86 out of 100 Evidence alignment'})).toBeVisible();
    expect(screen.getByText('FICTIONAL SAMPLE EVALUATION')).toBeVisible();
    expect(screen.getByText(evaluation.score_justification)).toBeVisible();
    let panel = screen.getByRole('tabpanel');
    expect(within(panel).getByText('React development')).toBeVisible();
    expect(within(panel).getByText(evaluation.matched_requirements[0].evidence)).toBeVisible();
    expect(within(panel).getByText(evaluation.matched_requirements[0].reason)).toBeVisible();
    await user.click(screen.getByRole('tab', {name: /Partial evidence/}));
    panel = screen.getByRole('tabpanel');
    expect(within(panel).getByText('TypeScript ownership')).toBeVisible();
    expect(screen.queryByText('React development')).not.toBeInTheDocument();
    await user.click(screen.getByRole('tab', {name: /Not evidenced/}));
    panel = screen.getByRole('tabpanel');
    expect(within(panel).getByText('Production accessibility audit')).toBeVisible();
    expect(within(panel).getByText(/does not establish that the candidate lacks the skill/)).toBeVisible();
    expect(screen.getAllByRole('tab')).toHaveLength(3);
    expect(screen.queryByRole('tab', {name: /Resume evidence/})).not.toBeInTheDocument();
    expect(screen.queryByText('Shipped a shared component library for three teams.')).not.toBeInTheDocument();
    expect(screen.getByText(/Model: test-model · Prompt: test-v1 · Rubric: test-v1/)).toBeVisible();
  });

  it('supports keyboard tab navigation and connects the selected tab to its panel', async () => {
    renderDetail();
    const supported = await screen.findByRole('tab', {name: /Supported/});
    supported.focus();
    await userEvent.keyboard('{ArrowRight}');
    const partial = screen.getByRole('tab', {name: /Partial evidence/});
    expect(partial).toHaveFocus();
    expect(partial).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', partial.id);
    await userEvent.keyboard('{ArrowLeft}');
    expect(supported).toHaveFocus();
    expect(supported).toHaveAttribute('aria-selected', 'true');
    await userEvent.keyboard('{ArrowLeft}');
    const missing = screen.getByRole('tab', {name: /Not evidenced/});
    expect(missing).toHaveFocus();
    expect(missing).toHaveAttribute('aria-selected', 'true');
    await userEvent.keyboard('{ArrowRight}');
    expect(supported).toHaveFocus();
    expect(supported).toHaveAttribute('aria-selected', 'true');
  });

  it('never invents a score or evidence when an evaluation is pending', async () => {
    vi.mocked(api.candidate).mockResolvedValue(pendingCandidate);
    renderDetail();
    expect(await screen.findByText('The evidence is still coming together')).toBeVisible();
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
    expect(screen.queryByRole('img', {name: /out of 100/})).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'View resume'})).toBeEnabled();
    await userEvent.click(screen.getByRole('button', {name: 'Check for an update'}));
    await waitFor(() => expect(api.candidate).toHaveBeenCalledTimes(2));
  });

  it('displays loading and a retryable error for failed candidate detail retrieval', async () => {
    const request = deferred<Candidate>();
    vi.mocked(api.candidate).mockReturnValueOnce(request.promise).mockResolvedValueOnce(highCandidate);
    renderDetail();
    expect(screen.getByRole('status', {name: 'Loading'})).toBeVisible();
    await act(async () => request.reject(new Error('Candidate not available for this requirement')));
    expect(await screen.findByRole('alert')).toHaveTextContent('Candidate not available for this requirement');
    await userEvent.click(screen.getByRole('button', {name: 'Try again'}));
    expect(await screen.findByRole('heading', {name: 'Alex Sample'})).toBeVisible();
  });

  it('fetches the authorized resume with session credentials and recovers from a document error', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValueOnce(new Response(JSON.stringify({detail: 'Resume access temporarily unavailable'}), {status: 503, headers: {'Content-Type': 'application/json'}})).mockResolvedValueOnce(new Response(new Blob(['%PDF-test'], {type: 'application/pdf'}), {headers: {'Content-Type': 'application/pdf'}}));
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test-resume-preview');
    renderDetail();
    await userEvent.click(await screen.findByRole('button', {name: 'View resume'}));
    const dialog = await screen.findByRole('dialog', {name: 'Candidate resume'});
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Resume access temporarily unavailable');
    expect(fetchMock).toHaveBeenCalledWith(`/api/hr/applications/${highCandidate.application_id}/resume?requirement_id=${engineeringJob.requirement_id}`, {credentials: 'include'});
    await userEvent.click(within(dialog).getByRole('button', {name: 'Try again'}));
    expect(await within(dialog).findByTitle('Alex Sample resume preview')).toHaveAttribute('src', 'blob:test-resume-preview');
    expect(within(dialog).getByRole('link', {name: 'Download resume'})).toHaveAttribute('download', 'alex-resume.pdf');
  });
});
