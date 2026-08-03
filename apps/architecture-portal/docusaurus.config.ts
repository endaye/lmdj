import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'LMDJ Product Manual',
  tagline: 'LMDJ 产品、架构与交付说明书',
  favicon: 'img/logo.svg',
  url: 'https://lmdj.netlify.app',
  baseUrl: '/',
  future: {v4: true},
  onBrokenLinks: 'throw',
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
          versions: {current: {label: '当前 main', path: ''}},
        },
        blog: false,
        theme: {customCss: './src/css/custom.css'},
      } satisfies Preset.Options,
    ],
  ],
  themeConfig: {
    colorMode: {respectPrefersColorScheme: true},
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
      style: 'dark',
      copyright: 'LMDJ internal product manual · publicly readable',
    },
    prism: {theme: prismThemes.github, darkTheme: prismThemes.dracula},
  } satisfies Preset.ThemeConfig,
};

export default config;
