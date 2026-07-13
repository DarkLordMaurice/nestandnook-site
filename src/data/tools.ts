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
  {
    slug: 'apartment-pet-zone-planner',
    title: 'Apartment Pet Zone Planner',
    shortTitle: 'Pet Zone Planner',
    description: 'Place feeding, water, hygiene, sleep, enrichment, and supply zones on a simple apartment map, then check the plan for traffic and separation conflicts.',
    category: 'Pet Care',
    status: 'live',
    href: '/tools/apartment-pet-zone-planner/',
    eyebrow: 'Pet-friendly layout tool',
    relatedGuides: [
      { label: 'Small-Space Pet Care Setup Guide', href: '/pet-care/small-space-pet-care-setup-guide/' },
      { label: 'How to Set Up a Pet Feeding Station in a Small Kitchen', href: '/pet-care/how-to-set-up-a-pet-feeding-station-in-a-small-kitchen/' },
      { label: 'Best Pet Food Storage Containers for Small Apartments', href: '/pet-care/best-pet-food-storage-containers-small-apartments/' },
    ],
  },
  {
    slug: 'fold-away-workbench-fit-planner',
    title: 'Fold-Away Workbench Fit Planner',
    shortTitle: 'Workbench Fit Planner',
    description: 'Compare a fold-away workbench against wall width, parked-car clearance, open working depth, and the passage left when folded.',
    category: 'Garage',
    status: 'live',
    href: '/tools/fold-away-workbench-fit-planner/',
    eyebrow: 'Map both garage modes before buying',
    relatedGuides: [
      { label: 'Best Fold-Away Workbenches for a Small Garage', href: '/garage/best-fold-away-workbenches-small-garage/' },
      { label: 'How to Set Up a Workspace in a One-Car Garage', href: '/garage/how-to-set-up-a-workspace-in-a-one-car-garage/' },
      { label: 'How to Maximize Vertical Space in a Small Garage', href: '/garage/how-to-maximize-vertical-space-in-a-small-garage/' },
    ],
  },
];

export const LIVE_TOOLS = TOOLS.filter((tool) => tool.status === 'live');
