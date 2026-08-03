import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  manual: [
    'overview/index',
    {type: 'category', label: '产品', items: ['product/positioning', 'product/capability-map', 'product/workflows']},
    {type: 'category', label: 'Core Modules', items: [
      'core/modules/foundation', 'core/modules/authoring-domain', 'core/modules/project-io',
      'core/modules/project-cooker', 'core/modules/audio-runtime', 'core/modules/provider-sdk',
      'core/modules/application-facade',
    ]},
    {type: 'category', label: 'Hosts', items: [
      'hosts/overview', 'hosts/core-cli', 'hosts/core-mcp', 'hosts/native-test-host', 'hosts/web-runtime',
    ]},
    {type: 'category', label: 'Providers', items: ['providers/overview', 'providers/local-proof']},
    {type: 'category', label: 'Contracts', items: [
      'contracts/overview', 'contracts/project', 'contracts/runtime-snapshot', 'contracts/capability',
      'contracts/assembly', 'contracts/error-module-version',
    ]},
    {type: 'category', label: 'Assembly', items: ['assembly/lmdj']},
    {type: 'category', label: 'Platform', items: [
      'platform/native-audio', 'platform/web-runtime', 'platform/storage', 'platform/input',
    ]},
    {type: 'category', label: 'Operations', items: [
      'operations/testing-and-proof', 'operations/version-and-release',
      'operations/documentation-governance',
    ]},
    {type: 'category', label: 'History', items: ['history/legacy-patch-architecture']},
  ],
};

export default sidebars;
