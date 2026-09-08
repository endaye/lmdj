import {createHash} from 'node:crypto';
import path from 'node:path';
import {readFile, lstat, readdir} from 'node:fs/promises';

function fail(message) {
  throw new Error(`portal facts error: ${message}`);
}

function relativePath(repoRoot, consumer) {
  const relative = path.relative(repoRoot, consumer);
  return relative && !relative.startsWith('..') ? relative.split(path.sep).join('/') : path.basename(consumer);
}

function productBuildText(value) {
  if (value === undefined || value === null) return '<missing>';
  return typeof value === 'string' && /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/.test(value)
    ? value
    : '<invalid>';
}

function productBuildMismatch({repoRoot, expected, found, consumer, remedy}) {
  let message = `Product Build mismatch: expected ${expected} from products/lmdj/version.json, found ${productBuildText(found)} in ${relativePath(repoRoot, consumer)}`;
  if (remedy) message += `; remedy: ${remedy}`;
  fail(message);
}

async function readJson(file) {
  try {
    return JSON.parse(await readFile(file, 'utf8'));
  } catch (error) {
    fail(`cannot read ${file}: ${error.message}`);
  }
}

async function sha256(file) {
  const bytes = await readFile(file);
  return createHash('sha256').update(bytes).digest('hex');
}

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.keys(value).sort().map((key) => [key, canonicalize(value[key])]),
    );
  }
  return value;
}

function canonicalJson(value) {
  return `${JSON.stringify(canonicalize(value))}\n`;
}

function sortIdentities(values) {
  if (!Array.isArray(values)) fail('component inventory must be an array');
  return [...values].sort((left, right) => left.id.localeCompare(right.id));
}

function identities(values) {
  return sortIdentities(values).map(({id, version}) => ({id, version}));
}

async function directChildPaths(root, name) {
  const entries = await readdir(root, {withFileTypes: true});
  const matches = [];
  for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
    if (!entry.isDirectory()) continue;
    const candidate = path.join(root, entry.name, name);
    if (await lstat(candidate).catch(() => null)) matches.push(candidate);
  }
  return matches;
}

async function recursiveNamedPaths(root, name) {
  const matches = [];
  for (const entry of (await readdir(root, {withFileTypes: true}))
    .sort((left, right) => left.name.localeCompare(right.name))) {
    const candidate = path.join(root, entry.name);
    if (entry.isDirectory()) matches.push(...await recursiveNamedPaths(candidate, name));
    else if (entry.name === name) matches.push(candidate);
  }
  return matches;
}

async function componentSource(repoRoot, field, componentId) {
  let matches;
  if (field === 'contracts') {
    matches = await directChildPaths(
      path.join(repoRoot, 'contracts'), `${componentId}.schema.json`,
    );
  } else {
    const root = {modules: 'packages', hosts: 'apps', providers: 'providers'}[field];
    if (!root) fail(`unknown component field ${field}`);
    const candidates = await directChildPaths(path.join(repoRoot, root), 'module.json');
    matches = [];
    for (const candidate of candidates.sort()) {
      const manifest = await readJson(candidate);
      if (manifest.module === componentId) matches.push(candidate);
    }
  }
  if (matches.length !== 1) fail(`${field} component ${componentId} must resolve exactly once`);
  const source = matches[0];
  if ((await lstat(source)).isSymbolicLink()) fail(`component source cannot be a symlink: ${source}`);
  return source;
}

async function validateSourceIdentity(field, entry, source) {
  const document = await readJson(source);
  if (field === 'contracts') {
    if (path.basename(source, '.schema.json') !== entry.id) fail(`contract source id mismatch for ${entry.id}`);
    if (document['x-lmdj-contract-version'] !== entry.version) {
      fail(`contract source version mismatch for ${entry.id}`);
    }
    return;
  }
  if (document.contract !== 'lmdj.module.v1') fail(`invalid module manifest for ${entry.id}`);
  if (document.module !== entry.id || document.version !== entry.version) {
    fail(`module source identity mismatch for ${entry.id}`);
  }
}

async function sourcePackageSha256(repoRoot, format, identity, files) {
  const members = [];
  for (const file of [...files].sort()) {
    const info = await lstat(file).catch(() => null);
    if (!info?.isFile() || info.isSymbolicLink()) fail(`source-package file is unavailable: ${file}`);
    const relative = path.relative(repoRoot, file).split(path.sep).join('/');
    if (relative.startsWith('../')) fail(`source-package file is outside the repository: ${file}`);
    members.push({path: relative, sha256: await sha256(file)});
  }
  return createHash('sha256')
    .update(canonicalJson({files: members, format, ...identity}))
    .digest('hex');
}

async function expectedComponentSha(repoRoot, field, entry, source) {
  if (field !== 'providers') return sha256(source);
  const providerRoot = path.dirname(source);
  const headers = await recursiveNamedPaths(path.join(providerRoot, 'include'), 'factory.hpp');
  if (headers.length !== 1) fail(`Provider ${entry.id} must have exactly one factory header`);
  return sourcePackageSha256(
    repoRoot,
    'provider-source-package',
    {provider_id: entry.id, provider_version: entry.version},
    [headers[0], source, path.join(providerRoot, 'src/provider.cpp')],
  );
}

async function validateInventory(repoRoot, assembly, lock, field) {
  const expected = identities(assembly[field]);
  const locked = identities(lock[field]);
  if (JSON.stringify(expected) !== JSON.stringify(locked)) fail(`${field} inventory mismatch`);
  for (const entry of sortIdentities(lock[field])) {
    const source = await componentSource(repoRoot, field, entry.id);
    await validateSourceIdentity(field, entry, source);
    const expectedSha = await expectedComponentSha(repoRoot, field, entry, source);
    if (entry.sha256 !== expectedSha) fail(`${field} source hash mismatch for ${entry.id}`);
  }
}

export async function readRepoFacts({repoRoot, revision, channel}) {
  const version = await readJson(path.join(repoRoot, 'products/lmdj/version.json'));
  const assemblyPath = path.join(repoRoot, 'products/lmdj/assembly.json');
  const assembly = await readJson(assemblyPath);
  const lockPath = path.join(repoRoot, 'products/lmdj/assembly.lock.json');
  const lockBytes = await readFile(lockPath).catch((error) => fail(`cannot read ${lockPath}: ${error.message}`));
  let lock;
  try {
    lock = JSON.parse(lockBytes);
  } catch (error) {
    fail(`cannot parse ${lockPath}: ${error.message}`);
  }

  const parts = [version.milestone, version.minor, version.build, version.patch];
  if (!parts.every((part) => Number.isInteger(part) && part >= 0)) {
    fail('product version must contain four non-negative integers');
  }
  const productVersion = parts.join('.');
  if (assembly.product?.id !== 'lmdj' || assembly.product?.version !== productVersion) {
    productBuildMismatch({
      repoRoot, expected: productVersion, found: assembly.product?.version, consumer: assemblyPath,
      remedy: 'update the reviewed products/lmdj/assembly.json declaration to the approved Product Build, then regenerate the compiled assembly and lock with scripts/version.py lock',
    });
  }
  if (lock.product?.id !== 'lmdj' || lock.product?.version !== productVersion) {
    productBuildMismatch({
      repoRoot, expected: productVersion, found: lock.product?.version, consumer: lockPath,
      remedy: 'regenerate the compiled assembly and lock with scripts/version.py lock',
    });
  }
  const productAssembly = lock.product_assembly;
  if (productAssembly?.id !== 'lmdj' || productAssembly?.version !== productVersion) {
    productBuildMismatch({
      repoRoot, expected: productVersion, found: productAssembly?.version, consumer: lockPath,
      remedy: 'regenerate the compiled assembly and lock with scripts/version.py lock',
    });
  }
  if (!revision || !channel) fail('revision and channel are required');

  if (lock.assembly_sha256 !== await sha256(assemblyPath)) fail('assembly source hash mismatch');
  for (const field of ['modules', 'hosts', 'providers', 'contracts']) {
    await validateInventory(repoRoot, assembly, lock, field);
  }

  const expectedProductAssemblySha = await sourcePackageSha256(
    repoRoot,
    'product-assembly-source-package',
    {product_id: 'lmdj', product_version: productVersion},
    [path.join(repoRoot, 'products/lmdj/CMakeLists.txt'), path.join(repoRoot, 'products/lmdj/src/compiled_assembly.cpp')],
  );
  if (productAssembly.sha256 !== expectedProductAssemblySha) fail('product assembly source hash mismatch');

  return {
    schema_version: 1,
    product: {id: 'lmdj', version: productVersion},
    channel,
    revision,
    assembly_lock_sha256: createHash('sha256').update(lockBytes).digest('hex'),
    modules: sortIdentities(lock.modules),
    hosts: sortIdentities(lock.hosts),
    providers: sortIdentities(lock.providers),
    contracts: sortIdentities(lock.contracts),
  };
}
