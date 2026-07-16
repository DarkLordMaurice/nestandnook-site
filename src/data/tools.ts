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
    slug: 'space-and-the-stars',
    title: 'Your Space, Written in the Stars',
    shortTitle: 'Space & the Stars',
    description: 'Pick your sign. Find out why your home is exactly like you — for better and worse.',
    category: 'Lifestyle',
    status: 'live',
    href: '/tools/space-and-the-stars/',
    eyebrow: 'Your space has always been written in the stars',
    relatedGuides: [
      { label: 'What Kind of Small-Space Person Are You?', href: '/tools/your-small-space-personality/' },
      { label: 'Small Kitchen Setup Guide', href: '/kitchen/small-kitchen-setup-guide/' },
      { label: 'Small Home Office Setup Guide', href: '/home-office/small-home-office-setup-guide/' },
      { label: 'Best Litter Boxes for Small Apartments', href: '/pet-care/best-litter-boxes-for-small-apartments/' },
    ],
  },
  {
    slug: 'your-small-space-personality',
    title: 'What Kind of Small-Space Person Are You?',
    shortTitle: 'Small-Space Personality Quiz',
    description: 'Six questions. One honest result. Find out which small-space type you are and where to actually start.',
    category: 'Lifestyle',
    status: 'live',
    href: '/tools/your-small-space-personality/',
    eyebrow: 'Know thyself, then organize',
    relatedGuides: [
      { label: 'Your Space, Written in the Stars', href: '/tools/space-and-the-stars/' },
      { label: 'Small Kitchen Setup Guide', href: '/kitchen/small-kitchen-setup-guide/' },
      { label: 'Small Home Office Setup Guide', href: '/home-office/small-home-office-setup-guide/' },
      { label: 'How to Organize a Small Kitchen With No Pantry', href: '/kitchen/how-to-organize-a-small-kitchen-with-no-pantry/' },
    ],
  },
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
      { label: 'How to Set Up a Pet Feeding Station in a Small Kitchen', href: '/pet-care/how-to-set-up-a-pet-feeding-station-in-a-small-kitchen/' },
      { label: 'Best Pet Food Storage Containers for Small Apartments', href: '/pet-care/best-pet-food-storage-containers-small-apartments/' },
      { label: 'Best Litter Boxes for Small Apartments', href: '/pet-care/best-litter-boxes-for-small-apartments/' },
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
  {
    slug: 'why-doesnt-this-feel-done-yet',
    title: "Why Doesn't This Feel Done Yet?",
    shortTitle: 'Why Doesn\'t This Feel Done?',
    description: 'A five-question diagnostic for the one room that still bugs you — find the actual root cause before buying anything else.',
    category: 'Lifestyle',
    status: 'live',
    href: '/tools/why-doesnt-this-feel-done-yet/',
    eyebrow: 'A diagnosis, not a shopping list',
    relatedGuides: [
      { label: 'Small Home Office Setup Guide', href: '/home-office/small-home-office-setup-guide/' },
      { label: 'Desk Cable Management', href: '/home-office/desk-cable-management/' },
      { label: 'How to Sit Correctly at a Small Desk', href: '/home-office/how-to-sit-correctly-at-a-small-desk/' },
      { label: 'What Kind of Small-Space Person Are You?', href: '/tools/your-small-space-personality/' },
    ],
  },
  {
    slug: 'regret-proof-purchase-check',
    title: 'The Regret-Proof Purchase Check',
    shortTitle: 'Regret-Proof Purchase Check',
    description: 'Six honest questions to run before you check out — this tool has no products to sell you, just a straight read on whether you actually need it.',
    category: 'Lifestyle',
    status: 'live',
    href: '/tools/regret-proof-purchase-check/',
    eyebrow: 'Run this before you check out',
    relatedGuides: [
      { label: "Why Doesn't This Feel Done Yet?", href: '/tools/why-doesnt-this-feel-done-yet/' },
      { label: 'Small Kitchen Starter Kit Under $100', href: '/kitchen/small-kitchen-starter-kit-under-100/' },
      { label: 'Small Home Office Setup Guide', href: '/home-office/small-home-office-setup-guide/' },
    ],
  },
  {
    slug: 'roast-my-space',
    title: 'Roast My Space',
    shortTitle: 'Roast My Space',
    description: 'Check every confession that\'s true and get an honest, funny read on your space — plus one real move to actually try.',
    category: 'Lifestyle',
    status: 'live',
    href: '/tools/roast-my-space/',
    eyebrow: 'Every space has one spot it\'s not proud of',
    relatedGuides: [
      { label: 'How to Organize a Small Pantry', href: '/kitchen/how-to-organize-a-small-pantry/' },
      { label: 'Desk Cable Management', href: '/home-office/desk-cable-management/' },
      { label: 'How to Organize a Small Fridge', href: '/kitchen/how-to-organize-a-small-fridge/' },
      { label: 'Small Home Office Setup Guide', href: '/home-office/small-home-office-setup-guide/' },
    ],
  },
];

export const LIVE_TOOLS = TOOLS.filter((tool) => tool.status === 'live');
