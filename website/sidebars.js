/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  tutorial: [
    {type: 'doc', id: 'start', label: 'Intro'},
    {type: 'doc', id: 'install', label: 'Installation'},
    {type: 'doc', id: 'prerequisites', label: 'Pre-requisites'},
    {type: 'html', value: '<hr class="sidebar-divider" aria-hidden="true" />'},
    {
      type: 'category',
      label: 'Build your specification',
      link: {type: 'doc', id: 'wizard'},
      collapsed: false,
      items: [
        {
          type: 'category',
          label: 'Guided interview',
          link: {type: 'doc', id: 'wizard-interview'},
          collapsed: false,
          items: ['product-requirements', 'test-scenarios'],
        },
        {type: 'doc', id: 'manual-specification', label: 'Configure manually'},
      ],
    },
    {
      type: 'category',
      label: 'Run your evaluations',
      link: {type: 'doc', id: 'run-evaluation'},
      collapsed: false,
      items: ['run-test-suite', 'run-graders'],
    },
    {type: 'doc', id: 'report', label: 'Analyse your results'},
    {type: 'doc', id: 'library', label: 'View our graders'},
    {type: 'html', value: '<hr class="sidebar-divider" aria-hidden="true" />'},
    {type: 'doc', id: 'examples', label: 'Examples'},
  ],
};

export default sidebars;
