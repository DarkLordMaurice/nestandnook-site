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
];

export const LIVE_TOOLS = TOOLS.filter((tool) => tool.status === 'live');
