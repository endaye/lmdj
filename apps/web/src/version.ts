export interface BuildEnvironment {
  VITE_PRODUCT_VERSION?: string;
  VITE_BUILD_REVISION?: string;
}

export interface BuildIdentity {
  productVersion: string;
  revision: string;
  shortRevision: string;
}

export function readBuildIdentity(env: BuildEnvironment): BuildIdentity {
  const productVersion = env.VITE_PRODUCT_VERSION?.trim() || "dev";
  const revision = env.VITE_BUILD_REVISION?.trim() || "unknown";
  return {
    productVersion,
    revision,
    shortRevision: revision === "unknown" ? revision : revision.slice(0, 8),
  };
}

export function formatBuildIdentity(identity: BuildIdentity): string {
  return `[LMDJ] ${identity.productVersion} · ${identity.shortRevision}`;
}

export function logBuildIdentity(
  identity: BuildIdentity,
  logger: (message: string) => void = (message) => console.info(message),
): void {
  logger(formatBuildIdentity(identity));
}

export const BUILD_IDENTITY = readBuildIdentity(import.meta.env);
export const PRODUCT_VERSION = BUILD_IDENTITY.productVersion;
