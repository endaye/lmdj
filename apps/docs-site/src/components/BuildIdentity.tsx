import React from 'react';
import facts from '@site/src/generated/site-facts.json';
import versionFacts from '@site/src/generated/version-facts.json';
import {useDocsVersion} from '@docusaurus/plugin-content-docs/client';

type IdentityKind = 'modules' | 'hosts' | 'providers' | 'contracts';

export function BuildIdentity({kind, id}: {kind?: IdentityKind; id?: string}) {
  const docsVersion = useDocsVersion();
  const snapshots = versionFacts as Record<string, typeof facts>;
  const selectedFacts = docsVersion.version === 'current' ? facts : (snapshots[docsVersion.version] ?? facts);
  const identity = kind && id
    ? selectedFacts[kind].find((candidate) => candidate.id === id)
    : undefined;
  return (
    <aside className="build-identity" aria-label="构建身份">
      <span><strong>Product Build</strong> {selectedFacts.product.version}</span>
      {identity && <span><strong>{identity.id}</strong> {identity.version}</span>}
      <span><strong>Channel</strong> {selectedFacts.channel}</span>
      <span title={selectedFacts.revision}><strong>Revision</strong> {selectedFacts.revision.slice(0, 12)}</span>
      <span><strong>页面</strong> {docsVersion.version === 'current' ? 'current main（非正式快照）' : `正式快照 ${docsVersion.version}`}</span>
    </aside>
  );
}
