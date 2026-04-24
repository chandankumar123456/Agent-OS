import React from 'react';
import { render, waitFor, act } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useNavigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './AuthContext';

function Probe() {
  const auth = useAuth();
  return <div data-testid="state">{auth.isAuthenticated ? 'yes' : 'no'}</div>;
}

function NavigationProbe() {
  const auth = useAuth();
  const navigate = useNavigate();
  return (
    <div>
      <div data-testid="state">{auth.isAuthenticated ? 'yes' : 'no'}</div>
      <button data-testid="navigate" onClick={() => navigate('/other')}>
        Navigate
      </button>
    </div>
  );
}

test('expired token logs out', async () => {
  localStorage.setItem('user', JSON.stringify({ id: '1', email: 'x@test.com', created_at: 'now' }));
  localStorage.setItem('accessToken', 'eyJhbGciOiJub25lIn0.eyJleHAiOjF9.');

  const { getByTestId } = render(
    <AuthProvider>
      <Probe />
    </AuthProvider>
  );

  await waitFor(() => expect(getByTestId('state')).toHaveTextContent('no'));
});

test('invalid token logs out', async () => {
  localStorage.setItem('user', JSON.stringify({ id: '1', email: 'x@test.com', created_at: 'now' }));
  localStorage.setItem('accessToken', 'not-a-jwt');

  const { getByTestId } = render(
    <AuthProvider>
      <Probe />
    </AuthProvider>
  );

  await waitFor(() => expect(getByTestId('state')).toHaveTextContent('no'));
});

test('auth state persists across navigation', async () => {
  // Use a valid-looking token (far future expiry)
  const validToken =
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.' +
    'eyJzdWIiOiIxIiwiZW1haWwiOiJ4QHRlc3QuY29tIiwiZXhwIjo5OTk5OTk5OTk5fQ.' +
    'signature';
  localStorage.setItem('user', JSON.stringify({ id: '1', email: 'x@test.com', created_at: 'now' }));
  localStorage.setItem('accessToken', validToken);

  const { getByTestId } = render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route path="/dashboard" element={<NavigationProbe />} />
          <Route path="/other" element={<NavigationProbe />} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>
  );

  // Wait for rehydration to complete
  await waitFor(() => expect(getByTestId('state')).toHaveTextContent('yes'));

  // Simulate client-side navigation (no page reload)
  act(() => {
    getByTestId('navigate').click();
  });

  // Auth state must remain true after navigation
  await waitFor(() => expect(getByTestId('state')).toHaveTextContent('yes'));
});

test('401 response clears auth state', async () => {
  const validToken =
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.' +
    'eyJzdWIiOiIxIiwiZW1haWwiOiJ4QHRlc3QuY29tIiwiZXhwIjo5OTk5OTk5OTk5fQ.' +
    'signature';
  localStorage.setItem('user', JSON.stringify({ id: '1', email: 'x@test.com', created_at: 'now' }));
  localStorage.setItem('accessToken', validToken);

  const { getByTestId } = render(
    <AuthProvider>
      <Probe />
    </AuthProvider>
  );

  await waitFor(() => expect(getByTestId('state')).toHaveTextContent('yes'));

  // Simulate a 401 API response (the API client dispatches auth:expired on 401)
  act(() => {
    window.dispatchEvent(
      new CustomEvent('auth:expired', { detail: { status: 401, message: 'Unauthorized' } })
    );
  });

  // Auth state should be cleared on 401
  await waitFor(() => expect(getByTestId('state')).toHaveTextContent('no'));
  expect(localStorage.getItem('accessToken')).toBeNull();
});
