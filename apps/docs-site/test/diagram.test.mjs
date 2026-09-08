import assert from 'node:assert/strict';
import test from 'node:test';
import {renderDiagram, validateDiagram} from '../scripts/lib/diagram.mjs';

function fixtureDiagram() {
  return {
    schema_version: 1,
    meta: {title: 'Fixture', summary: 'Deterministic diagram'},
    boundaries: [],
    components: [
      {id: 'a', label: 'Input', kind: 'host', x: 80, y: 120, width: 220, height: 100},
      {id: 'b', label: 'Output', kind: 'core', x: 460, y: 120, width: 220, height: 100},
    ],
    connections: [{from: 'a', to: 'b', label: 'request'}],
    cards: [{title: 'Rule', body: 'A deterministic card'}],
  };
}

test('renderer is deterministic and records the source digest', () => {
  const source = fixtureDiagram();
  const first = renderDiagram(source);
  const second = renderDiagram(source);
  assert.equal(first.svg, second.svg);
  assert.equal(first.html, second.html);
  assert.equal(first.sourceSha256, second.sourceSha256);
  assert.match(first.svg, new RegExp(`data-source-sha256="${first.sourceSha256}"`));
});

test('validator rejects overlaps and missing edge endpoints', () => {
  const source = fixtureDiagram();
  source.components[1] = {...source.components[1], x: 180};
  source.connections = [{from: 'a', to: 'missing'}];
  assert.deepEqual(validateDiagram(source), [
    'components a and b overlap',
    'connection a -> missing references unknown component missing',
  ]);
});
