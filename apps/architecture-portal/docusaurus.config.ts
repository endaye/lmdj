import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';
import {existsSync, readFileSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const portalRoot = path.dirname(fileURLToPath(import.meta.url));
const versionsPath = path.join(portalRoot, 'versions.json');
const frozenVersions: string[] = existsSync(versionsPath)
  ? JSON.parse(readFileSync(versionsPath, 'utf8'))
  : [];
const versions = Object.fromEntries([
  ['current', {label: '当前 main', path: ''}],
  ...frozenVersions.map((version) => [version, {label: `Product Build ${version}`, path: `versions/${version}`}]),
]);

const config: Config = {
  title: 'LMDJ Product Manual',
  tagline: 'LMDJ 产品、架构与交付说明书',
  favicon: 'img/logo.svg',
  url: 'https://lmdj.netlify.app',
  baseUrl: '/',
  future: {v4: true},
  onBrokenLinks: 'throw',
  onBrokenAnchors: 'throw',
  i18n: {defaultLocale: 'zh-Hans', locales: ['zh-Hans']},
  presets: [
    [
      'classic',
      {
        docs: {
          routeBasePath: '/',
          sidebarPath: './sidebars.ts',
          includeCurrentVersion: true,
          lastVersion: 'current',
          versions,
        },
        blog: false,
        theme: {customCss: './src/css/custom.css'},
      } satisfies Preset.Options,
    ],
  ],
  themeConfig: {
    colorMode: {respectPrefersColorScheme: true, disableSwitch: true},
    metadata: [
      {name: 'description', content: 'LMDJ 产品、架构与交付说明书：Core Modules、Hosts、Providers、Contracts、Assembly 与运营证据的唯一发布源。'},
    ],
    docs: {sidebar: {hideable: true, autoCollapseCategories: true}},
    navbar: {
      title: 'LMDJ Manual',
      logo: {alt: 'LMDJ', src: 'img/logo.svg'},
      items: [
        {type: 'docSidebar', sidebarId: 'manual', label: '产品说明书', position: 'left'},
        {to: '/product/capability-map', label: '能力地图', position: 'left'},
        {to: '/assembly/lmdj', label: '当前装配', position: 'left'},
        {type: 'docsVersionDropdown', position: 'right'},
        {href: 'https://github.com/endaye/lmdj', label: 'Repository', position: 'right'},
      ],
    },
    footer: {
      links: [
        {
          title: '说明书',
          items: [
            {label: '产品定位', to: '/product/positioning'},
            {label: 'Headless Core 总览', to: '/core/overview'},
            {label: 'Hosts', to: '/hosts/overview'},
            {label: 'Contracts', to: '/contracts/overview'},
          ],
        },
        {
          title: '交付与证据',
          items: [
            {label: '当前装配', to: '/assembly/lmdj'},
            {label: '能力地图', to: '/product/capability-map'},
            {label: '测试与 Proof', to: '/operations/testing-and-proof'},
            {label: '版本与发布', to: '/operations/version-and-release'},
          ],
        },
        {
          title: '治理',
          items: [
            {label: '文档治理', to: '/operations/documentation-governance'},
            {label: 'Repository', href: 'https://github.com/endaye/lmdj'},
          ],
        },
      ],
      copyright: 'LMDJ internal product manual · publicly readable',
    },
    prism: {theme: prismThemes.github, darkTheme: prismThemes.dracula},
  } satisfies Preset.ThemeConfig,
};

export default config;
