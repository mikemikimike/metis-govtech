import {themes} from 'prism-react-renderer';

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: 'METIS',
  tagline: 'Measurement and Evaluation of Trustworthy Intelligent Systems',
  url: 'http://localhost:3000',
  baseUrl: '/',
  favicon: 'img/metis-mark.png',
  onBrokenLinks: 'throw',
  markdown: {
    hooks: {onBrokenMarkdownLinks: 'throw'},
  },
  presets: [
    [
      'classic',
      {
        docs: {
          path: '../docs/tutorial',
          routeBasePath: '/',
          sidebarPath: './sidebars.js',
        },
        blog: false,
        theme: {customCss: './src/css/custom.css'},
      },
    ],
  ],
  themeConfig: {
    colorMode: {defaultMode: 'light', respectPrefersColorScheme: false},
    prism: {
      theme: themes.github,
      darkTheme: themes.oneDark,
      additionalLanguages: ['bash', 'yaml'],
    },
    navbar: {
      title: 'METIS',
      logo: {alt: 'METIS', src: 'img/metis-mark.png'},
      items: [
        {
          type: 'html',
          position: 'left',
          value: '<span class="navbar-docs-label">Documentation</span>',
        },
        {
          href: 'https://github.com/govtech-responsibleai/metis',
          label: 'GitHub',
          position: 'right',
          className: 'navbar-github',
        },
      ],
    },
  },
};

export default config;
