import path from 'node:path';
import {existsSync} from 'node:fs';

export const AREAS = new Set([
  'overview', 'product', 'core', 'hosts', 'providers', 'contracts',
  'assembly', 'platform', 'operations', 'history',
]);

export const STATUSES = new Set(['implemented', 'partial', 'designed', 'planned', 'retired']);

function validateStringArray({file, data, key, required, errors}) {
  const value = data[key];
  if (value == null && !required) return [];
  if (!Array.isArray(value) || value.length === 0 || value.some((item) => typeof item !== 'string' || !item)) {
    errors.push(`${file}: ${key} must be a non-empty string array`);
    return [];
  }
  return value;
}

export function validatePageMetadata({file, data, body, repoRoot, activeContractIds}) {
  const errors = [];
  for (const key of ['title', 'area', 'status', 'owners', 'source_paths']) {
    if (data[key] == null) errors.push(`${file}: missing ${key}`);
  }
  if (typeof data.title !== 'string' || !data.title.trim()) errors.push(`${file}: title must be a non-empty string`);
  if (data.area != null && !AREAS.has(data.area)) errors.push(`${file}: invalid area ${data.area}`);
  if (data.status != null && !STATUSES.has(data.status)) errors.push(`${file}: invalid status ${data.status}`);
  if (data.status === 'retired' && data.area !== 'history') {
    errors.push(`${file}: retired pages must be under history`);
  }

  validateStringArray({file, data, key: 'owners', required: true, errors});
  const sourcePaths = validateStringArray({file, data, key: 'source_paths', required: true, errors});
  const decisionPaths = validateStringArray({file, data, key: 'decision_paths', required: false, errors});
  for (const sourcePath of [...sourcePaths, ...decisionPaths]) {
    const resolved = path.resolve(repoRoot, sourcePath);
    const relative = path.relative(repoRoot, resolved);
    if (relative.startsWith('..') || path.isAbsolute(relative)) {
      errors.push(`${file}: path escapes repository ${sourcePath}`);
    } else if (!existsSync(resolved)) {
      errors.push(`${file}: missing source path ${sourcePath}`);
    }
  }

  if (data.area !== 'history') {
    if (/lmdj\.(patch|materials)\.v1/.test(body)) {
      errors.push(`${file}: retired Contract leaked into current documentation`);
    }
    const mentioned = new Set(body.match(/lmdj\.[a-z0-9-]+(?:\.[a-z0-9-]+)*\.v\d+/g) ?? []);
    for (const contractId of mentioned) {
      if (!activeContractIds.has(contractId)) {
        errors.push(`${file}: retired Contract ID ${contractId} is not active`);
      }
    }
  }
  return errors;
}
