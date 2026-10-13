import type {ReactElement} from 'react';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {render} from '@testing-library/react';
import {MemoryRouter, Route, Routes} from 'react-router-dom';
import {afterEach, vi} from 'vitest';
import {api} from '../lib/api';
import {AuthProvider} from '../lib/auth';
import {candidateResponse, engineeringJob, highCandidate, jobs, session} from './fixtures';

const clients: QueryClient[] = [];
afterEach(() => {clients.splice(0).forEach(client => client.clear());});

export function mockApi() {
  vi.spyOn(api, 'session').mockResolvedValue(session());
  vi.spyOn(api, 'jobs').mockResolvedValue(jobs);
  vi.spyOn(api, 'job').mockResolvedValue(engineeringJob);
  vi.spyOn(api, 'applications').mockResolvedValue([highCandidate]);
  vi.spyOn(api, 'application').mockResolvedValue(highCandidate);
  vi.spyOn(api, 'candidates').mockResolvedValue(candidateResponse([highCandidate]));
  vi.spyOn(api, 'candidate').mockResolvedValue(highCandidate);
  vi.spyOn(api, 'submit').mockResolvedValue({success: true, application_id: 'TEST-SUBMITTED-001', ai_status: 'queued', message: 'Your fictional test application was received.'});
}

export function renderPage(page: ReactElement, {path = '/', route = '*'}: {path?: string; route?: string} = {}) {
  const client = new QueryClient({defaultOptions: {queries: {retry: false, gcTime: Infinity}, mutations: {retry: false}}});
  clients.push(client);
  return {...render(<QueryClientProvider client={client}><AuthProvider><MemoryRouter initialEntries={[path]}><Routes><Route path={route} element={page} /></Routes></MemoryRouter></AuthProvider></QueryClientProvider>), client};
}

export function renderRoutes(routes: ReactElement, path: string) {
  const client = new QueryClient({defaultOptions: {queries: {retry: false, gcTime: Infinity}}});
  clients.push(client);
  return render(<QueryClientProvider client={client}><AuthProvider><MemoryRouter initialEntries={[path]}><Routes>{routes}</Routes></MemoryRouter></AuthProvider></QueryClientProvider>);
}

export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {resolve = resolvePromise; reject = rejectPromise;});
  return {promise, resolve, reject};
}
