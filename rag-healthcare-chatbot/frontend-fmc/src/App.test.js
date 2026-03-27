import { render, screen } from '@testing-library/react';
import App from './App';

jest.mock('react-markdown', () => ({ children }) => children);
jest.mock('remark-gfm', () => () => null);
jest.mock('remark-gemoji', () => () => null);
jest.mock('lottie-web', () => ({
  loadAnimation: () => ({
    destroy: jest.fn(),
  }),
}));

beforeEach(() => {
  global.fetch = jest.fn(() =>
    Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ v: '5.9.6', fr: 30, ip: 0, op: 1, w: 10, h: 10, layers: [] }),
    })
  );
});

afterEach(() => {
  jest.resetAllMocks();
});

test('renders KinexAssist chat greeting', () => {
  render(<App />);
  expect(screen.getByText(/how can i assist you with clinical data today/i)).toBeInTheDocument();
});
