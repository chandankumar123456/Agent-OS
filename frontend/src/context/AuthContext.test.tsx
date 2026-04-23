import React from 'react';
import { render, waitFor } from '@testing-library/react';
import { AuthProvider, useAuth } from './AuthContext';

function Probe() {
  const auth = useAuth();
  return <div data-testid="state">{auth.isAuthenticated ? 'yes' : 'no'}</div>;
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
