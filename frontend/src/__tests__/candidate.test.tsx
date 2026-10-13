import {act, fireEvent, screen, waitFor, within} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import {api} from '../lib/api';
import type {Job, SubmissionResult} from '../lib/types';
import {ApplicationDetailPage, ApplicationsPage, ApplyPage, JobDetailsPage, JobsPage} from '../pages/candidate';
import {engineeringJob, highCandidate, jobs, pendingCandidate, session} from './fixtures';
import {deferred, mockApi, renderPage} from './helpers';

beforeEach(mockApi);

describe('public opportunities', () => {
  it('lists API jobs and applies search, team, location, work mode, and contract filters together', async () => {
    const user = userEvent.setup();
    renderPage(<JobsPage />);
    expect(await screen.findByRole('link', {name: 'Frontend Engineer'})).toBeVisible();
    expect(screen.getByRole('link', {name: 'Product Designer'})).toBeVisible();
    await user.type(screen.getByRole('textbox', {name: 'Search jobs'}), 'Figma');
    expect(screen.queryByRole('link', {name: 'Frontend Engineer'})).not.toBeInTheDocument();
    await user.selectOptions(screen.getByRole('combobox', {name: 'department'}), 'Design');
    await user.selectOptions(screen.getByRole('combobox', {name: 'location'}), 'Remote');
    await user.selectOptions(screen.getByRole('combobox', {name: 'work mode'}), 'Remote');
    await user.selectOptions(screen.getByRole('combobox', {name: 'employment type'}), 'Contract');
    expect(screen.getByText('1 opportunity to explore')).toBeVisible();
    await user.selectOptions(screen.getByRole('combobox', {name: 'department'}), 'Engineering');
    expect(screen.getByText('No matches just yet')).toBeVisible();
    await user.click(screen.getAllByRole('button', {name: 'Clear filters'})[0]);
    expect(screen.getByRole('link', {name: 'Frontend Engineer'})).toBeVisible();
    expect(screen.getByRole('link', {name: 'Product Designer'})).toBeVisible();
  });

  it('initializes the listing from URL search and handles an empty source', async () => {
    renderPage(<JobsPage />, {path: '/jobs?search=TypeScript'});
    expect(await screen.findByRole('link', {name: 'Frontend Engineer'})).toBeVisible();
    expect(screen.getByRole('textbox', {name: 'Search jobs'})).toHaveValue('TypeScript');
    expect(screen.queryByRole('link', {name: 'Product Designer'})).not.toBeInTheDocument();
  });

  it('shows a meaningful empty state when there are no open jobs', async () => {
    vi.mocked(api.jobs).mockResolvedValue([]);
    renderPage(<JobsPage />);
    expect(await screen.findByText('Your next chapter is coming')).toBeVisible();
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
  });

  it('shows loading and recovers from a job-list failure using the retry control', async () => {
    const request = deferred<Job[]>();
    vi.mocked(api.jobs).mockReturnValueOnce(request.promise).mockResolvedValueOnce(jobs);
    renderPage(<JobsPage />);
    expect(screen.getByRole('status', {name: 'Loading'})).toBeVisible();
    await act(async () => request.reject(new Error('Job service unavailable')));
    expect(await screen.findByRole('alert')).toHaveTextContent('Job service unavailable');
    await userEvent.click(screen.getByRole('button', {name: 'Try again'}));
    expect(await screen.findByRole('link', {name: 'Frontend Engineer'})).toBeVisible();
    expect(api.jobs).toHaveBeenCalledTimes(2);
  });

  it('renders the selected job details and carries the requirement into the apply link', async () => {
    renderPage(<JobDetailsPage />, {path: `/jobs/${engineeringJob.requirement_id}`, route: '/jobs/:requirementId'});
    expect(await screen.findByRole('heading', {name: engineeringJob.title, level: 1})).toBeVisible();
    expect(api.job).toHaveBeenCalledWith(engineeringJob.requirement_id);
    expect(screen.getByText(engineeringJob.description)).toBeVisible();
    expect(screen.getByText('React')).toBeVisible();
    expect(screen.getByText('Accessibility')).toBeVisible();
    expect(screen.getByRole('link', {name: 'Apply now'})).toHaveAttribute('href', `/jobs/${engineeringJob.requirement_id}/apply`);
  });
});

function renderApply() {
  return renderPage(<ApplyPage />, {path: `/jobs/${engineeringJob.requirement_id}/apply`, route: '/jobs/:requirementId/apply'});
}
async function readyForm() {
  await screen.findByRole('heading', {name: 'Make your next move.'});
  // Auth and job requests are independent; wait until the verified profile arrives.
  await waitFor(() => expect(screen.getByRole('textbox', {name: 'Full name'})).toHaveValue('Alex Sample'));
}
async function attachResume() {
  await userEvent.upload(screen.getByLabelText('Upload resume'), new File(['%PDF-test resume'], 'sample.pdf', {type: 'application/pdf'}));
}

describe('candidate application submission', () => {
  it('keeps verified identity read-only and blocks submission without informed consent', async () => {
    renderApply(); await readyForm(); await attachResume();
    expect(screen.getByRole('textbox', {name: 'Full name'})).toHaveAttribute('readonly');
    expect(screen.getByRole('textbox', {name: 'Email address'})).toHaveValue('alex@example.test');
    await userEvent.click(screen.getByRole('button', {name: 'Submit application'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Please accept the privacy consent to continue.');
    expect(api.submit).not.toHaveBeenCalled();
  });

  it('requires a resume even after consent is accepted', async () => {
    renderApply(); await readyForm();
    await userEvent.click(screen.getByRole('checkbox'));
    await userEvent.click(screen.getByRole('button', {name: 'Submit application'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Please attach your resume.');
    expect(api.submit).not.toHaveBeenCalled();
  });

  it.each([
    ['unsupported file type', new File(['text'], 'resume.txt', {type: 'text/plain'}), 'Please upload a PDF or DOCX document.'],
    ['empty document', new File([], 'resume.pdf', {type: 'application/pdf'}), 'Your resume file is empty. Please choose another document.'],
    ['document over 10 MB', new File([new Uint8Array(10 * 1024 * 1024 + 1)], 'resume.pdf', {type: 'application/pdf'}), 'Your resume must be 10 MB or smaller.'],
  ])('rejects an %s before any network submission', async (_, file, message) => {
    renderApply(); await readyForm();
    fireEvent.change(screen.getByLabelText('Upload resume'), {target: {files: [file]}});
    expect(screen.getByRole('alert')).toHaveTextContent(message);
    await userEvent.click(screen.getByRole('checkbox'));
    await userEvent.click(screen.getByRole('button', {name: 'Submit application'}));
    expect(api.submit).not.toHaveBeenCalled();
  });

  it('validates LinkedIn profile URLs before transmitting the application', async () => {
    renderApply(); await readyForm(); await attachResume();
    await userEvent.type(screen.getByRole('textbox', {name: /LinkedIn profile/}), 'https://malicious.example/profile');
    await userEvent.click(screen.getByRole('checkbox'));
    await userEvent.click(screen.getByRole('button', {name: 'Submit application'}));
    expect(await screen.findByText(/Enter an HTTPS LinkedIn profile URL/)).toBeVisible();
    expect(api.submit).not.toHaveBeenCalled();
  });

  it('sends multipart consent and selected requirement, disables repeated submits, and confirms the returned reference', async () => {
    const request = deferred<SubmissionResult>();
    vi.mocked(api.submit).mockReturnValueOnce(request.promise);
    renderApply(); await readyForm(); await attachResume();
    await userEvent.type(screen.getByRole('textbox', {name: /Phone number/}), '+91 9876543210');
    await userEvent.click(screen.getByRole('checkbox'));
    await userEvent.click(screen.getByRole('button', {name: 'Submit application'}));
    await waitFor(() => expect(api.submit).toHaveBeenCalledTimes(1));
    const [body, idempotencyKey] = vi.mocked(api.submit).mock.calls[0];
    expect(body.get('requirement_id')).toBe(engineeringJob.requirement_id);
    expect(body.get('resume')).toBeInstanceOf(File);
    expect(body.get('phone')).toBe('+91 9876543210');
    expect(body.get('consent_accepted')).toBe('true');
    expect(body.get('consent_version')).toBe('v1');
    expect(idempotencyKey).toMatch(/^[\da-f]{8}-[\da-f-]{27}$/i);
    expect(screen.getByTestId('submit-application')).toBeDisabled();
    expect(screen.getByLabelText('Upload resume')).toBeDisabled();
    await act(async () => request.resolve({success: true, application_id: 'TEST-CONFIRMED-007', ai_status: 'queued', message: 'Application safely received.'}));
    expect(await screen.findByTestId('application-success')).toHaveTextContent('Application safely received.');
    expect(screen.getByTestId('application-id')).toHaveTextContent('TEST-CONFIRMED-007');
    expect(screen.getByRole('link', {name: 'Follow your application'})).toHaveAttribute('href', '/candidate/applications/TEST-CONFIRMED-007');
    expect(screen.getByText(/does not score your uploaded resume/)).toBeVisible();
  });

  it('preserves the uploaded document and idempotency key when retrying a failed submission', async () => {
    vi.mocked(api.submit).mockRejectedValueOnce(new Error('Document storage temporarily unavailable'));
    renderApply(); await readyForm(); await attachResume();
    await userEvent.click(screen.getByRole('checkbox'));
    await userEvent.click(screen.getByRole('button', {name: 'Submit application'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Document storage temporarily unavailable');
    expect(screen.getByText('sample.pdf')).toBeVisible();
    expect(screen.getByTestId('submit-application')).toBeEnabled();
    await userEvent.click(screen.getByRole('button', {name: 'Submit application'}));
    expect(await screen.findByTestId('application-success')).toBeVisible();
    expect(api.submit).toHaveBeenCalledTimes(2);
    expect(vi.mocked(api.submit).mock.calls[1][1]).toBe(vi.mocked(api.submit).mock.calls[0][1]);
  });

  it('shows and submits the consent version supplied by the authenticated session', async () => {
    vi.mocked(api.session).mockResolvedValue({...session(), consent_version: 'test-consent-v2'});
    renderApply(); await readyForm(); await attachResume();
    expect(screen.getByText(/Consent version test-consent-v2/)).toBeVisible();
    await userEvent.click(screen.getByRole('checkbox'));
    await userEvent.click(screen.getByRole('button', {name: 'Submit application'}));
    await screen.findByTestId('application-success');
    expect(vi.mocked(api.submit).mock.calls[0][0].get('consent_version')).toBe('test-consent-v2');
  });
});

describe('candidate status visibility', () => {
  it('links application records and separates application status from AI processing', async () => {
    vi.mocked(api.applications).mockResolvedValue([pendingCandidate]);
    renderPage(<ApplicationsPage />);
    const row = await screen.findByRole('row', {name: /Frontend Engineer/});
    expect(within(row).getByText('Submitted')).toBeVisible();
    expect(within(row).getByText('Queued')).toBeVisible();
    expect(within(row).getByRole('link', {name: 'Frontend Engineer'})).toHaveAttribute('href', `/candidate/applications/${pendingCandidate.application_id}`);
    expect(screen.queryByText(/86\/100/)).not.toBeInTheDocument();
  });

  it('shows candidate-owned details without exposing internal evaluation evidence', async () => {
    renderPage(<ApplicationDetailPage />, {path: `/candidate/applications/${highCandidate.application_id}`, route: '/candidate/applications/:applicationId'});
    expect(await screen.findByText(highCandidate.resume_file_name)).toBeVisible();
    expect(api.application).toHaveBeenCalledWith(highCandidate.application_id);
    expect(screen.queryByText(highCandidate.evaluation!.score_justification)).not.toBeInTheDocument();
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
    expect(screen.getByText(/Processing status is separate from a hiring decision/)).toBeVisible();
  });
});
