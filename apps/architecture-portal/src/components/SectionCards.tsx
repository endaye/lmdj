import React from 'react';
import Link from '@docusaurus/Link';
import {StatusBadge, type PortalStatus} from './StatusBadge';

export type SectionCard = {
  title: string;
  description: string;
  to: string;
  status: PortalStatus;
};

export function SectionCards({items}: {items: SectionCard[]}) {
  return (
    <div className="section-cards">
      {items.map((item) => (
        <Link className="section-card" to={item.to} key={item.to}>
          <div><h3>{item.title}</h3><StatusBadge status={item.status} /></div>
          <p>{item.description}</p>
        </Link>
      ))}
    </div>
  );
}
