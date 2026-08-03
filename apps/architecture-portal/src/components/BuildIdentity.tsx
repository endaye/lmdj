import React from 'react';
import facts from '@site/src/generated/site-facts.json';

type IdentityKind = 'modules' | 'hosts' | 'providers' | 'contracts';

export function BuildIdentity({kind, id}: {kind?: IdentityKind; id?: string}) {
  const identity = kind && id
    ? facts[kind].find((candidate) => candidate.id === id)
    : undefined;
  return (
    <aside className="build-identity" aria-label="构建身份">
      <span><strong>Product Build</strong> {facts.product.version}</span>
      {identity && <span><strong>{identity.id}</strong> {identity.version}</span>}
      <span><strong>Channel</strong> {facts.channel}</span>
      <span title={facts.revision}><strong>Revision</strong> {facts.revision.slice(0, 12)}</span>
      <span><strong>页面</strong> current main（非正式快照）</span>
    </aside>
  );
}
