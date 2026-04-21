import { render, waitFor } from '@testing-library/react';
import Dashboard from './Dashboard';

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
  render(<Dashboard />);

  await waitFor(() => expect(document.body.textContent).toContain('tasks failed'));
});
