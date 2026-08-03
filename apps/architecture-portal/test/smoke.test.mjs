import assert from 'node:assert/strict';
import test from 'node:test';
import {smokePortal} from '../scripts/lib/smoke.mjs';

function fakeResponses(responses) {
  return async (url) => {
    const pathname = new URL(url).pathname;
    const response = responses[pathname] ?? {status: 404, type: 'text/plain', body: 'missing'};
    return {
      status: response.status,
      headers: {get: (name) => name.toLowerCase() === 'content-type' ? response.type : null},
      text: async () => response.body,
    };
  };
}

test('smoke rejects raw source and wrong identity', async () => {
  const errors = await smokePortal({
    baseUrl: 'https://example.netlify.app',
    productBuild: '1.0.13.0',
    revision: 'abcdef1',
    routes: ['/'],
    fetchImpl: fakeResponses({
      '/': {status: 200, type: 'text/plain; charset=UTF-8', body: '<!DOCTYPE html>'},
    }),
  });
  assert.deepEqual(errors, [
    '/ returned content-type text/plain; charset=UTF-8',
    '/ did not render Product Build 1.0.13.0',
    '/ did not render revision abcdef1',
  ]);
});

test('smoke accepts rendered HTML and verifies referenced assets', async () => {
  const errors = await smokePortal({
    baseUrl: 'https://example.netlify.app',
    productBuild: '1.0.13.0',
    revision: 'abcdef1',
    routes: ['/'],
    fetchImpl: fakeResponses({
      '/': {status: 200, type: 'text/html; charset=UTF-8', body: '<html><body>Product Build 1.0.13.0 Revision abcdef1<script src="/assets/app.js"></script></body></html>'},
      '/assets/app.js': {status: 200, type: 'text/javascript', body: 'console.log("ok")'},
    }),
  });
  assert.deepEqual(errors, []);
});
