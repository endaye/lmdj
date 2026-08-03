import React from 'react';

export function DiagramFrame({title, html, svg}: {title: string; html: string; svg: string}) {
  return (
    <figure className="diagram-frame">
      <iframe title={title} src={html} loading="lazy" />
      <figcaption>
        <strong>{title}</strong>
        <span><a href={html}>独立 HTML</a> · <a href={svg}>SVG</a></span>
      </figcaption>
    </figure>
  );
}
