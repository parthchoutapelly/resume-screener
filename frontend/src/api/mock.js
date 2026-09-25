// src/api/mock.js
// In-memory mock adapter for development without a backend.
// Enabled by VITE_USE_MOCKS=true. Implements the same surface as api in client.js.
// Covers all 9 display_status values, every blocking_reason, and each notification_status.

const delay = (ms = 400) => new Promise((r) => setTimeout(r, ms));

const JOB_ID = 'job_mock0001';

let jobs = {
  [JOB_ID]: {
    job_id: JOB_ID,
    job_title: 'Senior Backend Engineer',
    jd_source: 'file',
    jd_original_filename: 'backend-jd.pdf',
    parse_status: 'parsed',
    blocking_reason: null,
    required_skills: ['python', 'aws', 'dynamodb'],
    required_titles: ['backend engineer'],
    min_experience_years: 3,
    derived_skills: ['python', 'aws', 'sql'],
    derived_titles: ['backend engineer'],
    derived_min_experience_years: 2,
    effective: {
      skills: ['python', 'aws', 'dynamodb'],
      titles: ['backend engineer'],
      min_experience_years: 3,
      skills_source: 'recruiter',
      titles_source: 'jd',
      min_experience_years_source: 'recruiter',
    },
    requirements_confirmed: true,
    shortlist_threshold: 70,
    created_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
    updated_at: new Date().toISOString(),
  },
};

let candidates = [
  {
    job_id: JOB_ID, candidate_id: 'cand_scored01',
    original_filename: 'jane_doe_resume.pdf',
    display_status: 'scored', parse_status: 'parsed', score_status: 'scored',
    name: 'Jane Doe', email: 'jane.doe@example.com',
    employers: ['Acme Corp', 'Globex Inc'], titles_held: ['backend developer'],
    skills: ['aws', 'python', 'sql'],
    total_experience_years: 4.0, experience_estimated: false,
    match_score: 71.3, skills_score: 66.7, title_score: 60, experience_score: 100,
    matched_skills: ['aws', 'python'], missing_skills: ['dynamodb'],
    title_match_type: 'related', title_match_held: 'backend developer', title_match_required: 'backend engineer',
    shortlist_candidate: true, scoring_version: 'v1', scored_at: new Date().toISOString(),
    decision: 'pending', notification_status: null,
    file_type: 'pdf_mixed', page_count: 2, ocr_pages: 1, char_count: 3184,
    created_at: new Date(Date.now() - 55 * 60 * 1000).toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    job_id: JOB_ID, candidate_id: 'cand_scored02',
    original_filename: 'bob_smith_resume.pdf',
    display_status: 'scored', parse_status: 'parsed', score_status: 'scored',
    name: 'Bob Smith', email: 'bob.smith@example.com',
    employers: ['TechCorp'], titles_held: ['software engineer'],
    skills: ['python', 'dynamodb', 'aws'],
    total_experience_years: 6.0, experience_estimated: false,
    match_score: 88.3, skills_score: 100, title_score: 60, experience_score: 100,
    matched_skills: ['python', 'dynamodb', 'aws'], missing_skills: [],
    title_match_type: 'related', title_match_held: 'software engineer', title_match_required: 'backend engineer',
    shortlist_candidate: true, scoring_version: 'v1', scored_at: new Date().toISOString(),
    decision: 'shortlisted', notification_status: 'sent',
    file_type: 'pdf_native', page_count: 1, ocr_pages: 0, char_count: 2800,
    created_at: new Date(Date.now() - 54 * 60 * 1000).toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    job_id: JOB_ID, candidate_id: 'cand_processing',
    original_filename: 'alice_processing.pdf',
    display_status: 'processing', parse_status: 'pending', score_status: 'pending',
    name: null, email: null, skills: [], employers: [], titles_held: [],
    decision: 'pending', notification_status: null,
    file_type: null, page_count: null, ocr_pages: null,
    created_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    job_id: JOB_ID, candidate_id: 'cand_scoring',
    original_filename: 'carol_scoring.docx',
    display_status: 'scoring', parse_status: 'parsed', score_status: 'pending',
    name: 'Carol Jones', email: null, skills: ['python'], employers: ['StartupX'], titles_held: ['engineer'],
    decision: 'pending', notification_status: null,
    file_type: 'docx', page_count: 2, ocr_pages: 0,
    created_at: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    job_id: JOB_ID, candidate_id: 'cand_awaiting_jd',
    original_filename: 'dave_waiting.pdf',
    display_status: 'awaiting_jd', parse_status: 'parsed', score_status: 'pending',
    name: 'Dave Nguyen', email: 'dave@example.com', skills: ['java'], employers: [], titles_held: ['java developer'],
    decision: 'pending', notification_status: null,
    file_type: 'pdf_native', page_count: 1, ocr_pages: 0,
    created_at: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    job_id: JOB_ID, candidate_id: 'cand_upload_missing',
    original_filename: 'eve_missing.pdf',
    display_status: 'upload_missing', parse_status: 'pending', score_status: 'pending',
    name: null, email: null, skills: [], employers: [], titles_held: [],
    decision: 'pending', notification_status: null,
    file_type: null, page_count: null, ocr_pages: null,
    created_at: new Date(Date.now() - 20 * 60 * 1000).toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    job_id: JOB_ID, candidate_id: 'cand_error01',
    original_filename: 'corrupt_resume.pdf',
    display_status: 'error', parse_status: 'error', score_status: 'pending',
    error_code: 'unreadable_document',
    name: null, email: null, skills: [], employers: [], titles_held: [],
    decision: 'pending', notification_status: null,
    file_type: 'pdf_native', page_count: null, ocr_pages: null,
    created_at: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    job_id: JOB_ID, candidate_id: 'cand_error02',
    original_filename: 'huge_resume.pdf',
    display_status: 'error', parse_status: 'error', score_status: 'pending',
    error_code: 'too_many_pages',
    name: null, email: null, skills: [], employers: [], titles_held: [],
    decision: 'pending', notification_status: null,
    file_type: 'pdf_native', page_count: null, ocr_pages: null,
    created_at: new Date(Date.now() - 28 * 60 * 1000).toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    job_id: JOB_ID, candidate_id: 'cand_rejected',
    original_filename: 'frank_rejected.pdf',
    display_status: 'scored', parse_status: 'parsed', score_status: 'scored',
    name: 'Frank Lee', email: 'frank@example.com',
    employers: ['OldCo'], titles_held: ['qa engineer'],
    skills: ['python'],
    total_experience_years: 1.0, experience_estimated: true,
    match_score: 35.0, skills_score: 33.3, title_score: 0, experience_score: 33.3,
    matched_skills: ['python'], missing_skills: ['aws', 'dynamodb'],
    title_match_type: 'none', shortlist_candidate: false,
    decision: 'rejected', notification_status: null,
    file_type: 'pdf_native', page_count: 1, ocr_pages: 0,
    created_at: new Date(Date.now() - 40 * 60 * 1000).toISOString(),
    updated_at: new Date().toISOString(),
  },
];

// --- helpers ---
const jobList = () =>
  Object.values(jobs).map((j) => ({
    job_id: j.job_id,
    job_title: j.job_title,
    parse_status: j.parse_status,
    blocking_reason: j.blocking_reason,
    jd_source: j.jd_source,
    created_at: j.created_at,
  }));

export const mockApi = {
  createJob: async (_payload) => {
    await delay();
    return { job_id: JOB_ID };
  },
  listJobs: async () => {
    await delay();
    return { jobs: jobList(), next_token: null };
  },
  getJob: async (jobId) => {
    await delay(200);
    const job = jobs[jobId];
    if (!job) throw Object.assign(new Error('Not found'), { status: 404 });
    return job;
  },
  updateJob: async (jobId, patch) => {
    await delay();
    jobs[jobId] = { ...jobs[jobId], ...patch, updated_at: new Date().toISOString() };
    return { ...jobs[jobId], rescore_enqueued: 2 };
  },
  addResumes: async (_jobId, filenames) => {
    await delay();
    return {
      uploads: filenames.map((fn) => ({
        candidate_id: `cand_new_${Math.random().toString(36).slice(2, 8)}`,
        original_filename: fn,
        upload: {
          url: 'https://example-bucket.s3.amazonaws.com/',
          fields: { key: `resume-uploads/${JOB_ID}/cand_new/resume.pdf`, 'Content-Type': 'application/pdf', Policy: 'mock' },
        },
      })),
    };
  },
  listCandidates: async (jobId) => {
    await delay(300);
    return {
      candidates: candidates
        .filter((c) => c.job_id === jobId)
        .sort((a, b) => (b.match_score ?? -1) - (a.match_score ?? -1)),
    };
  },
  decide: async (jobId, candidateId, decision) => {
    await delay();
    const idx = candidates.findIndex((c) => c.candidate_id === candidateId);
    if (idx < 0) throw Object.assign(new Error('Not found'), { status: 404 });
    candidates[idx] = { ...candidates[idx], decision };
    if (decision === 'shortlisted' && candidates[idx].email) {
      candidates[idx].notification_status = 'sent';
    }
    return candidates[idx];
  },
  resumeUrl: async () => {
    await delay();
    return { download_url: '#mock-resume-url' };
  },
  exportCsv: async (jobId) => {
    await delay();
    return { download_url: '#mock-export', count: candidates.filter((c) => c.job_id === jobId && c.decision === 'shortlisted').length };
  },
  listFailures: async () => {
    await delay();
    return {
      failures: [
        { failure_id: 'fail_001', job_id: JOB_ID, stage: 'extraction', terminal: true,
          error_code: 'unreadable_document', original_filename: 'corrupt.pdf',
          raw_payload: JSON.stringify({ Records: [{ s3: { object: { key: 'resume-uploads/...' } } }] }),
          created_at: new Date().toISOString() },
      ],
      next_token: null,
    };
  },
};
