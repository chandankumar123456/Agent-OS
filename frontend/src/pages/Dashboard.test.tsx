import React from 'react';
import { render, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import Dashboard from './Dashboard';
import { ToastProvider } from '../components/ToastProvider';

beforeAll(() => {
  class MockIntersectionObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }

  // @ts-expect-error test-only global stub
  globalThis.IntersectionObserver = MockIntersectionObserver;
});

vi.mock('../api/client', () => ({
  apiClient: {
    getMetrics: vi.fn().mockResolvedValue({ requests_total: 0, errors_total: 0, error_rate: 0, avg_response_time: 0 }),
    listTasks: vi.fn().mockRejectedValue(new Error('tasks failed')),
    pollTaskStatus: vi.fn(),
    createTask: vi.fn(),
    getTaskTrace: vi.fn(),
  },
}));

test('api failure is shown in the dashboard', async () => {
  render(
    <BrowserRouter>
      <ToastProvider>
        <Dashboard />
      </ToastProvider>
    </BrowserRouter>
  );

  await waitFor(() => expect(document.body.textContent).toContain('tasks failed'));
});
