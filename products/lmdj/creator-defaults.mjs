import catalog from "./assets/default-kit/catalog/index.json" with {type: "json"};
// Product Assembly owns the exact default identity; Hosts consume no manifest.
const entry = catalog.entries[0];
export const CREATOR_SOUND_SET_CATALOG_PATH = "/soundset-catalog/";
export const CREATOR_DEFAULT_SOUND_SET = Object.freeze({
  setId: entry.set_id, version: entry.version, manifestSha256: entry.manifest_sha256,
});
