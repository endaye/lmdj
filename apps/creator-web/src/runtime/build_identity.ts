// Build identity is derived from the generated Product Assembly identity at
// bundle time. It is display-only: the Runtime session still verifies the
// deployed manifest against the same values before any Project work starts.

export interface CreatorBuildIdentity {
  readonly productBuild: string;
  readonly hostId: string;
  readonly hostVersion: string;
  readonly platformVersion: string;
  readonly protocolVersion: number;
}

interface IdentitySource {
  readonly product_build: string;
  readonly protocol_version: number;
  readonly platform: {readonly version: string};
  readonly hosts: {
    readonly "creator-web": {
      readonly id: string;
      readonly version: string;
    };
  };
}

export function creatorBuildIdentity(
  source: IdentitySource,
): CreatorBuildIdentity {
  const host = source.hosts["creator-web"];
  return Object.freeze({
    productBuild: source.product_build,
    hostId: host.id,
    hostVersion: host.version,
    platformVersion: source.platform.version,
    protocolVersion: source.protocol_version,
  });
}

export function shortBuildLabel(identity: CreatorBuildIdentity): string {
  return `v${identity.productBuild} · ${identity.hostId} ${identity.hostVersion}`;
}

export function describeBuildIdentity(identity: CreatorBuildIdentity): string {
  return [
    `Product Build ${identity.productBuild}`,
    `${identity.hostId} ${identity.hostVersion}`,
    `web-runtime-platform ${identity.platformVersion}`,
    `protocol ${identity.protocolVersion}`,
  ].join(" · ");
}

export function announceBuildIdentity(
  identity: CreatorBuildIdentity,
  target: Pick<Console, "info"> = console,
): void {
  target.info(`LMDJ Creator ${describeBuildIdentity(identity)}`, identity);
}
