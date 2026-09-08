import React from 'react';

export type PortalStatus = 'implemented' | 'partial' | 'designed' | 'planned' | 'retired';

const labels: Record<PortalStatus, string> = {
  implemented: '已实现',
  partial: '部分实现',
  designed: '已设计',
  planned: '规划中',
  retired: '已退役',
};

export function StatusBadge({status}: {status: PortalStatus}) {
  return <span className={`status-badge status-${status}`}>{labels[status]}</span>;
}
