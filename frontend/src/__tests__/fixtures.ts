import type {AuthSession, Candidate, CandidateResponse, Evaluation, Job, LinkedInProfile, User} from '../lib/types';

// All people, employers, requirements, and scores here are fictional test fixtures.
export const candidateUser: User = {sub: 'test-candidate', name: 'Alex Sample', email: 'alex@example.test', role: 'candidate', issuer: 'test'};
export const hrUser: User = {sub: 'test-reviewer', name: 'Taylor Reviewer', email: 'taylor@example.test', role: 'hr', issuer: 'test'};
export const linkedinProfile: LinkedInProfile = {
  sub: 'urn:li:member:test-15030', issuer: 'https://www.linkedin.com/oauth',
  name: 'Alex Sample', given_name: 'Alex', family_name: 'Sample',
  email: 'alex@example.test', email_verified: true, locale: 'en-US',
  picture: 'https://media.licdn.com/dms/image/test-avatar',
};
export function session(user: User | null = candidateUser): AuthSession {return {user, csrf_token: 'test-csrf-token', demo_mode: true};}

export const engineeringJob: Job = {
  requirement_id: 'TEST-ENG-001', title: 'Frontend Engineer', description: 'Build accessible recruitment experiences.',
  responsibilities: 'Develop and review reusable UI components.', required_skills: ['React', 'TypeScript'], preferred_skills: ['Accessibility'],
  qualifications: 'Experience delivering web applications.', department: 'Engineering', location: 'Bengaluru', work_mode: 'Hybrid',
  employment_type: 'Full-time', min_experience: 2, max_experience: 5, openings: 2, status: 'Open', published_date: '2026-09-01', deadline: '2026-11-01',
};
export const designJob: Job = {...engineeringJob, requirement_id: 'TEST-DES-002', title: 'Product Designer', department: 'Design', location: 'Remote', work_mode: 'Remote', employment_type: 'Contract', required_skills: ['Figma', 'Research'], preferred_skills: ['Prototyping']};
export const jobs = [engineeringJob, designJob];

export const evaluation: Evaluation = {
  score: 86, meets_minimum_criteria: true, match_label: 'Strong evidence', score_justification: 'React delivery is documented; backend ownership is not established.',
  summary: 'Fictional experience supports a frontend engineering review.', evaluation_confidence: 'High', model_deployment: 'test-model', prompt_version: 'test-v1', rubric_version: 'test-v1',
  matched_requirements: [{requirement: 'React development', resume_section: 'Projects', project_name: 'Accessible hiring portal', evidence: 'Built accessible React components for a hiring portal.', reason: 'The project explicitly documents React implementation.', evidence_strength: 'Strong'}],
  partially_matched_requirements: [{requirement: 'TypeScript ownership', resume_section: 'Skills', project_name: '', evidence: 'TypeScript is listed in technical skills.', reason: 'Project-level TypeScript responsibility is not described.', evidence_strength: 'Partial'}],
  not_evidenced_requirements: [{requirement: 'Production accessibility audit', reason: 'No audit result is included in the submitted document.'}],
  relevant_evidence: [{requirement: 'UI delivery', resume_section: 'Experience', project_name: 'Design system', evidence: 'Shipped a shared component library for three teams.', reason: 'A concrete delivery outcome is documented.', evidence_strength: 'Strong'}],
};

export const highCandidate: Candidate = {
  application_id: 'TEST-APP-001', candidate_id: 'TEST-CAN-001', requirement_id: engineeringJob.requirement_id, job_title: engineeringJob.title,
  candidate_name: 'Alex Sample', email: 'alex@example.test', applied_date: '2026-10-01', hr_status: 'Submitted', ai_status: 'completed',
  resume_file_name: 'alex-resume.pdf', linkedin_url: 'https://www.linkedin.com/in/alex-sample', evaluation, evaluation_date: '2026-10-02', demo_fixture: true,
};
export const lowerCandidate: Candidate = {...highCandidate, application_id: 'TEST-APP-002', candidate_id: 'TEST-CAN-002', candidate_name: 'Morgan Example', email: 'morgan@example.test', evaluation: {...evaluation, score: 62, match_label: 'Partial evidence'}};
export const pendingCandidate: Candidate = {...highCandidate, application_id: 'TEST-APP-003', candidate_id: 'TEST-CAN-003', candidate_name: 'Jamie Fixture', email: 'jamie@example.test', evaluation: null, evaluation_date: null, ai_status: 'queued'};
export const designCandidate: Candidate = {...highCandidate, application_id: 'TEST-APP-004', candidate_id: 'TEST-CAN-004', requirement_id: designJob.requirement_id, job_title: designJob.title, candidate_name: 'Casey Designer', email: 'casey@example.test', evaluation: {...evaluation, score: 95}};
export function candidateResponse(candidates: Candidate[]): CandidateResponse {return {candidates, limit: 25, returned_count: candidates.length};}
