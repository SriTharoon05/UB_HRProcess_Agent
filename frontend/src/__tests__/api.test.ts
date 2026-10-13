import {beforeEach, describe, expect, it, vi} from 'vitest';
import {api, ApiError, request, setCsrfToken} from '../lib/api';
import {session} from './fixtures';

beforeEach(() => setCsrfToken(''));

describe('authenticated API requests', () => {
  it('uses same-origin session credentials and binds CSRF returned by identity verification', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValueOnce(new Response(JSON.stringify(session()), {headers: {'Content-Type': 'application/json'}})).mockResolvedValueOnce(new Response('{"success":true}'));
    vi.stubGlobal('fetch', fetchMock);
    await api.session();
    await api.logout();
    expect(fetchMock.mock.calls[0][0]).toBe('/api/auth/me');
    expect(fetchMock.mock.calls[0][1]?.credentials).toBe('include');
    const logoutOptions = fetchMock.mock.calls[1][1]!;
    expect(logoutOptions.method).toBe('POST');
    expect(new Headers(logoutOptions.headers).get('X-CSRF-Token')).toBe('test-csrf-token');
    expect(logoutOptions.credentials).toBe('include');
  });

  it('preserves multipart boundary handling and the idempotency header on resume submissions', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response('{"success":true,"application_id":"TEST","ai_status":"queued","message":"Received"}'));
    vi.stubGlobal('fetch', fetchMock);
    setCsrfToken('test-submit-csrf');
    const form = new FormData(); form.set('resume', new File(['document'], 'sample.pdf', {type: 'application/pdf'}));
    await api.submit(form, 'test-stable-request-key');
    expect(fetchMock.mock.calls[0][0]).toBe('/api/applications');
    const options = fetchMock.mock.calls[0][1]!;
    const headers = new Headers(options.headers);
    expect(options.body).toBe(form);
    expect(headers.get('Idempotency-Key')).toBe('test-stable-request-key');
    expect(headers.get('X-CSRF-Token')).toBe('test-submit-csrf');
    expect(headers.has('Content-Type')).toBe(false);
  });

  it('encodes both requirement and application path segments for job-scoped evidence', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response('{}'));
    vi.stubGlobal('fetch', fetchMock);
    await api.candidate('REQ / &1', 'APP / &2');
    expect(fetchMock.mock.calls[0][0]).toBe('/api/hr/jobs/REQ%20%2F%20%261/candidates/APP%20%2F%20%262');
  });

  it('propagates a readable server error with its status', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({detail: 'HR role required'}), {status: 403})));
    const failure = request('/api/hr/jobs');
    await expect(failure).rejects.toBeInstanceOf(ApiError);
    await expect(failure).rejects.toMatchObject({message: 'HR role required', status: 403});
  });

  it('handles non-JSON gateway failures without exposing an HTML response', async () => {
    vi.stubGlobal('fetch', vi.fn<typeof fetch>().mockResolvedValue(new Response('<html>Private gateway diagnostics</html>', {status: 502})));
    await expect(request('/api/jobs')).rejects.toMatchObject({message: 'Request failed (502). Please try again.', status: 502});
  });
});
