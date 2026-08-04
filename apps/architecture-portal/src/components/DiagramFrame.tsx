import React, {useEffect, useRef} from 'react';
import useBaseUrl from '@docusaurus/useBaseUrl';
import {useColorMode} from '@docusaurus/theme-common';
import {useActiveDocContext} from '@docusaurus/plugin-content-docs/client';
import versionFacts from '@site/src/generated/version-facts.json';

const DIAGRAM_IDS = new Set([
  'application-facade', 'audio-runtime', 'authoring-domain', 'foundation',
  'lmdj-core', 'lmdj-product', 'project-cooker', 'project-io', 'provider-sdk',
]);

type DiagramFrameProps = {title: string; diagramId: string; html?: never; svg?: never} |
  {title: string; diagramId?: never; html: string; svg: string};

function legacyDiagramId(html: string | undefined, svg: string | undefined) {
  const htmlMatch = html?.match(/^\/diagrams\/([a-z0-9-]+)\.html$/);
  const svgMatch = svg?.match(/^\/diagrams\/([a-z0-9-]+)\.svg$/);
  return htmlMatch?.[1] === svgMatch?.[1] ? htmlMatch?.[1] : undefined;
}

export function DiagramFrame(props: DiagramFrameProps) {
  const {title} = props;
  const {activeVersion} = useActiveDocContext(undefined);
  if (!activeVersion) throw new Error('DiagramFrame requires an active documentation version');
  const metadata = (versionFacts as Record<string, {schema_version?: number}>)[activeVersion.name];
  const diagramId = 'diagramId' in props && props.diagramId
    ? props.diagramId
    : activeVersion.name === '1.0.13.0' && metadata?.schema_version === 1
      ? legacyDiagramId('html' in props ? props.html : undefined, 'svg' in props ? props.svg : undefined)
      : undefined;
  if (!diagramId || !DIAGRAM_IDS.has(diagramId)) throw new Error(`unknown architecture diagram ${diagramId}`);
  const frozen = activeVersion.name !== 'current' && metadata?.schema_version === 2;
  const assetBase = frozen
    ? `/versions/${activeVersion.name}/diagrams`
    : '/diagrams';
  const html = useBaseUrl(`${assetBase}/${diagramId}.html`);
  const svg = useBaseUrl(`${assetBase}/${diagramId}.svg`);
  const {colorMode} = useColorMode();
  const frameRef = useRef<HTMLIFrameElement>(null);
  const syncTheme = () => {
    frameRef.current?.contentWindow?.postMessage(
      {type: 'lmdj-diagram-theme', theme: colorMode},
      window.location.origin,
    );
  };
  useEffect(syncTheme, [colorMode]);
  return (
    <figure className="diagram-frame">
      <iframe ref={frameRef} title={title} src={html} loading="lazy" onLoad={syncTheme} />
      <figcaption>
        <strong>{title}</strong>
        <span><a href={html}>独立 HTML</a> · <a href={svg}>SVG</a></span>
      </figcaption>
    </figure>
  );
}
