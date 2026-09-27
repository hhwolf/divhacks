/** @vitest-environment jsdom */
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Room } from '@arp/contracts';
import { useEditor } from '../store';
import { RequestBar } from './RequestBar';

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const room: Room = {
  id: 'room-1',
  name: 'Test room',
  source: 'sample',
  skeleton: {
    floorPolygon: [[0, 0], [4, 0], [4, 3], [0, 3]],
    dimensions: { l: 4, w: 3, h: 2.8 },
    walls: [
      { x1: 0, z1: 0, x2: 4, z2: 0, height: 2.8 },
      { x1: 4, z1: 0, x2: 4, z2: 3, height: 2.8 },
      { x1: 4, z1: 3, x2: 0, z2: 3, height: 2.8 },
      { x1: 0, z1: 3, x2: 0, z2: 0, height: 2.8 },
    ],
    doors: [],
    windows: [],
    outlets: [],
  },
};

describe('RequestBar', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    window.HTMLDialogElement.prototype.showModal = vi.fn();
    window.HTMLDialogElement.prototype.close = vi.fn();
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const body = url.includes('rent-assessment') ? { assessment: null } : { profile: null };
      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }));
    useEditor.setState({ room, activeId: 'layout-1', requestOpen: false, furniture: {}, items: [], layouts: [], zones: [] });
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(() => {
    act(() => root.unmount());
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('keeps a visible rent popup entry point beside the ask button', async () => {
    await act(async () => root.render(createElement(RequestBar)));

    const rent = document.querySelector<HTMLButtonElement>('[data-testid="rent-fab"]');
    expect(rent?.textContent).toContain('Rent');
    expect(document.querySelector('[data-testid="request-fab"]')).not.toBeNull();

    await act(async () => rent!.click());

    expect(document.querySelector<HTMLDialogElement>('.housing-dialog')?.getAttribute('aria-label')).toBe('Rent & costs');
  });
});
