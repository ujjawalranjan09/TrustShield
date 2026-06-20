// k6 load test for the /api/v1/analyze endpoint
// Run: k6 run --vus 10 --duration 30s backend/tests/load/k6_analyze.js

import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.API_URL || 'http://localhost:8000';
const API_KEY = __ENV.API_KEY || '';

export const options = {
  vus: 10,
  duration: '30s',
  thresholds: {
    http_req_duration: ['p(95)<300'], // 95% under 300ms SLA
    http_req_failed: ['rate<0.01'],   // <1% errors
  },
};

const scamPayloads = [
  {
    messages: [{ sender: 'agent', text: 'otp batao mujhe apna' }],
    session_metadata: {
      client_app_id: 'loadtest', session_id: 'lt_' + Date.now(),
      contact_initiated_by: 'unknown', is_during_active_upi_session: true,
      user_device_hash: 'loadtest', prior_reports_for_sender: 0,
    },
  },
  {
    messages: [{ sender: 'agent', text: 'open anydesk my id is 123456789' }],
    session_metadata: {
      client_app_id: 'loadtest', session_id: 'lt_' + Date.now(),
      contact_initiated_by: 'unknown', is_during_active_upi_session: false,
      user_device_hash: 'loadtest', prior_reports_for_sender: 2,
    },
  },
  {
    messages: [{ sender: 'user', text: 'what time does the shop close' }],
    session_metadata: {
      client_app_id: 'loadtest', session_id: 'lt_' + Date.now(),
      contact_initiated_by: 'user', is_during_active_upi_session: false,
      user_device_hash: 'loadtest', prior_reports_for_sender: 0,
    },
  },
];

export default function () {
  const payload = scamPayloads[Math.floor(Math.random() * scamPayloads.length)];
  payload.session_metadata.session_id = 'lt_' + Date.now() + '_' + __ITER;

  const headers = { 'Content-Type': 'application/json' };
  if (API_KEY) headers['X-API-Key'] = API_KEY;

  const res = http.post(`${BASE_URL}/api/v1/analyze`, JSON.stringify(payload), { headers });

  check(res, {
    'status is 200': (r) => r.status === 200,
    'has risk_score': (r) => JSON.parse(r.body).risk_score !== undefined,
    'latency < 300ms': (r) => r.timings.duration < 300,
  });

  sleep(0.1);
}
