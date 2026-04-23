import React from 'react';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import Landing from './Landing';

beforeAll(() => {
  class MockIntersectionObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }

  // framer-motion viewport features expect this API in tests.
  // @ts-expect-error test-only global stub
  globalThis.IntersectionObserver = MockIntersectionObserver;
});

test('landing does not expose a fake documentation action', () => {
  render(
    <BrowserRouter>
      <Landing />
    </BrowserRouter>
  );

  expect(screen.queryByText('View Documentation')).toBeNull();
});
