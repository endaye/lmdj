import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {projectChangelogs} from './lib/host-changelogs.mjs';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
try {
  if (process.argv.length !== 3 || !['--write', '--check'].includes(process.argv[2])) {
    throw new Error('why: explicit changelog mode required; remedy: use --check or --write');
  }
  const pages = await projectChangelogs(repoRoot, {check: process.argv[2] === '--check'});
  console.log(`Host changelogs: ${pages.length} static projections ${process.argv[2] === '--check' ? 'valid' : 'generated'}`);
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
