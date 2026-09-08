import React from 'react';
import Link from '@docusaurus/Link';
import {useActiveDocContext} from '@docusaurus/plugin-content-docs/client';
import {StatusBadge, type PortalStatus} from './StatusBadge';

type CardContent = {
  title: string;
  description: string;
  status: PortalStatus;
};

export type SectionCard = CardContent & ({docId: string; to?: never} | {docId?: never; to: string});

function legacyDocId(to: string) {
  return to.replace(/^\/+|\/+$/g, '');
}

export function SectionCards({items}: {items: SectionCard[]}) {
  const {activeVersion} = useActiveDocContext(undefined);
  if (!activeVersion) throw new Error('SectionCards requires an active documentation version');
  const seen = new Set<string>();
  const resolved = items.map((item) => {
    const docId = 'docId' in item && item.docId
      ? item.docId
      : activeVersion.name === '1.0.13.0' && 'to' in item && typeof item.to === 'string'
        ? legacyDocId(item.to)
        : '';
    if (!docId || !/^[a-z0-9][a-z0-9/-]*$/.test(docId)) {
      throw new Error('SectionCards item requires a valid docId');
    }
    if (seen.has(docId)) throw new Error(`SectionCards contains duplicate docId ${docId}`);
    seen.add(docId);
    const matches = activeVersion.docs.filter((doc) => doc.id === docId);
    if (matches.length !== 1) {
      throw new Error(`SectionCards docId ${docId} resolved ${matches.length} times in ${activeVersion.name}`);
    }
    return {...item, docId, path: matches[0].path};
  });
  return (
    <div className="section-cards">
      {resolved.map((item) => (
        <Link className="section-card" to={item.path} key={item.docId}>
          <div><h3>{item.title}</h3><StatusBadge status={item.status} /></div>
          <p>{item.description}</p>
        </Link>
      ))}
    </div>
  );
}
