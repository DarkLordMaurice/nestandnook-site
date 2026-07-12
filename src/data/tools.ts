export type ToolStatus = 'live' | 'planned';

export interface ToolDefinition {
  slug: string;
  title: string;
  shortTitle: string;
  description: string;
  category: string;
  status: ToolStatus;
  href: string;
  eyebrow: string;
  relatedGuides: { label: string; href: string }[];
}

export const TOOLS: ToolDefinition[] = [
  {
    slug: 'counter-footprint-simulator',
    title: 'Counter Footprint Simulator',
    shortTitle: 'Counter Footprint Simulator',
    description: 'Check whether an appliance or prep tool physically fits your counter, preserves a usable prep zone, and deserves permanent counter space.',
    category: 'Kitchen',
    status: 'live',
    href: '/tools/counter-footprint-simulator/',
    eyebrow: 'Measure before the box arrives',
    relatedGuides: [
      { label: 'Complete Small-Space Kitchen Setup Guide', href: '/kitchen/small-kitchen-setup-guide/' },
      { label: 'Best Compact Air Fryers for Small Kitchens', href: '/kitchen/best-compact-air-fryers-small-kitchen/' },
      { label: 'How to Prep Food With Minimal Counter Space', href: '/kitchen/how-to-prep-food-with-minimal-counter-space/' },
      { label: 'Best Space-Saving Gadgets for Small Kitchens', href: '/kitchen/best-space-saving-gadgets-for-small-kitchens/' },
    ],
  },
  {
    slug: 'desk-fit-reality-check',
    title: 'Desk Fit Reality Check',
    shortTitle: 'Desk Fit Reality Check',
    description: 'Compare a desk, chair adjustment range, your measured seated proportions, and a footrest before buying a setup that cannot line up comfortably.',
    category: 'Home Office',
    status: 'live',
    href: '/tools/desk-fit-reality-check/',
    eyebrow: 'Make the measurements negotiate first',
    relatedGuides: [
      { label: 'How to Sit Correctly at a Small Desk', href: '/home-office/how-to-sit-correctly-at-a-small-desk/' },
      { label: 'Chair Too Low for Desk: Practical Fixes', href: '/home-office/chair-too-low-for-desk-fixes/' },
      { label: 'Best Footrests for Short People', href: '/home-office/best-footrest-for-short-people/' },
      { label: 'Small Home Office Setup Guide', href: '/home-office/small-home-office-setup-guide/' },
    ],
  },
];

export const LIVE_TOOLS = TOOLS.filter((tool) => tool.status === 'live');
