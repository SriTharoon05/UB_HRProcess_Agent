import '@testing-library/jest-dom/vitest';
import {cleanup} from '@testing-library/react';
import {afterEach, vi} from 'vitest';

afterEach(() => cleanup());

class TestResizeObserver implements ResizeObserver {
  constructor(private callback: ResizeObserverCallback) {}
  observe(target: Element) {
    this.callback([{
      target,
      contentRect: {width: 320, height: 145} as DOMRectReadOnly,
      borderBoxSize: [{inlineSize: 320, blockSize: 145}],
      contentBoxSize: [{inlineSize: 320, blockSize: 145}],
      devicePixelContentBoxSize: [{inlineSize: 320, blockSize: 145}],
    }], this);
  }
  unobserve() {}
  disconnect() {}
}

Object.defineProperty(globalThis, 'ResizeObserver', {value: TestResizeObserver, configurable: true});
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn((query: string) => ({matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn()})),
});
Object.defineProperty(URL, 'createObjectURL', {value: () => 'blob:test-document', configurable: true, writable: true});
Object.defineProperty(URL, 'revokeObjectURL', {value: () => undefined, configurable: true, writable: true});
