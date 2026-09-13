import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {resumeVersion} from './lib/version-docs.mjs';

const portalRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const [requestedVersion, channel, revision] = process.argv.slice(2);
if (process.argv.length !== 5) {
  console.error('usage: node scripts/resume-version.mjs PRODUCT_BUILD CHANNEL SOURCE_SHA');
  process.exit(64);
}
await resumeVersion({portalRoot, repoRoot: path.resolve(portalRoot, '../..'),
  requestedVersion, channel, revision});
console.log(`portal version: verified existing ${requestedVersion} (${channel}) at ${revision}`);
