// Drop 01 catalogue: the four pieces with real flats. Prices are indicative and
// every spec here is illustrative until the pieces are confirmed for release;
// the UI labels them that way.

export const DROP = {
  code: "DROP 01",
  status: "unreleased", // "unreleased" | "live" (no checkout is wired yet)
  statusLabel: "Not yet released",
};

export const SIZES = ["XS", "S", "M", "L", "XL", "XXL"];

export const COLOURS = {
  black: { id: "black", name: "Black", swatch: "#1d1a18" },
  grey: { id: "grey", name: "Grey", swatch: "#8e8984" },
};

// Image views per garment type; files are /art/<slug>-<colour>-<view>.webp from scripts/art_flats.py
const VIEW_LABELS = {
  front: "Front",
  back: "Back",
  "back-detail": "Back detail",
  "chest-detail": "Chest detail",
  "sleeve-detail": "Sleeve detail",
  "front-detail": "Print detail",
};

function colourways(slug, views, alts) {
  return ["black", "grey"].map((id) => ({
    ...COLOURS[id],
    images: views.map((view) => ({
      src: `/art/${slug}-${id}-${view}.webp`,
      thumb: `/art/${slug}-${id}-${view}-thumb.webp`,
      label: VIEW_LABELS[view],
      alt: `${alts[view]} ${COLOURS[id].name} colourway.`,
    })),
  }));
}

const HOODIE_BASE = [
  "Heavyweight brushed-back fleece",
  "Cropped, boxy body with dropped shoulders",
  "Full balloon sleeves gathered into ribbed cuffs",
  "Full-length zip and front pouch pocket",
  "FTD wordmark across the chest",
];
const HOODIE_FIT = "Cut boxy and cropped. Take your usual size for the intended shape, or size up for more length.";
const HOODIE_CHEST = "Close-up of the chest: the FTD wordmark split by the zip, above the pouch pocket.";

// Indicative garment measurements in centimetres, measured flat. Published for
// planning only: final grading is confirmed at release.
const TOP_GUIDE = {
  columns: ["Size", "Chest", "Length", "Sleeve"],
  rows: [
    ["XS", 60, 52, 58],
    ["S", 63, 54, 60],
    ["M", 66, 56, 62],
    ["L", 69, 58, 63],
    ["XL", 72, 60, 64],
    ["XXL", 75, 62, 65],
  ],
  note: "Centimetres, measured flat. Chest is pit to pit; length is shoulder to hem.",
};
const BOTTOM_GUIDE = {
  columns: ["Size", "Waist", "Inseam", "Leg opening"],
  rows: [
    ["XS", 34, 74, 26],
    ["S", 37, 76, 27],
    ["M", 40, 78, 28],
    ["L", 43, 80, 29],
    ["XL", 46, 81, 30],
    ["XXL", 49, 82, 31],
  ],
  note: "Centimetres, measured flat. Waist is relaxed, edge to edge; leg opening is across the hem.",
};

export const PRODUCTS = [
  {
    slug: "crossbone-zip-hoodie",
    name: "Crossbone Zip Hoodie",
    price: 120,
    cardView: 1, // the hoodies share a front, so cards lead with the back print
    summary:
      "Built for the long haul. Heavyweight construction, a cropped boxy silhouette, and custom crossbone artwork down the sleeves and across the shoulders. Made to be worn hard and kept longer.",
    details: [...HOODIE_BASE, "Crossbone artwork down both sleeves and across the back shoulders"],
    fit: HOODIE_FIT,
    sizeGuide: TOP_GUIDE,
    colours: colourways("crossbone-zip-hoodie", ["front", "back", "back-detail", "chest-detail", "sleeve-detail"], {
      front: "Crossbone Zip Hoodie, front: cropped zip hoodie with a white FTD wordmark across the chest, a pouch pocket, and ornate crossbone prints running down both balloon sleeves.",
      back: "Crossbone Zip Hoodie, back: two large ornate crossbone crosses printed diagonally across the shoulders, with the sleeve prints wrapping round.",
      "back-detail": "Close-up of the back print: two crossbone crosses with rosette centres and filigree ends.",
      "chest-detail": HOODIE_CHEST,
      "sleeve-detail": "Close-up of a sleeve: the crossbone print wrapping the balloon sleeve towards the cuff.",
    }),
  },
  {
    slug: "never-enough-zip-hoodie",
    cardView: 1,
    name: "Never Enough Zip Hoodie",
    price: 120,
    summary:
      "FTD on the chest. NEVER ENOUGH across the back in a thorned death-metal logo that spreads shoulder to shoulder. Cropped, boxy and heavy.",
    details: [...HOODIE_BASE, "NEVER ENOUGH logo across the back"],
    fit: HOODIE_FIT,
    sizeGuide: TOP_GUIDE,
    colours: colourways("never-enough-zip-hoodie", ["front", "back", "back-detail", "chest-detail"], {
      front: "Never Enough Zip Hoodie, front: cropped zip hoodie with a white FTD wordmark across the chest and a pouch pocket; plain balloon sleeves.",
      back: "Never Enough Zip Hoodie, back: the words Never Enough in a sprawling, thorned death-metal logo across the upper back.",
      "back-detail": "Close-up of the Never Enough back print, all spikes and dripping strokes.",
      "chest-detail": HOODIE_CHEST,
    }),
  },
  {
    slug: "cross-zip-hoodie",
    cardView: 1,
    name: "Cross Zip Hoodie",
    price: 120,
    summary:
      "FTD on the chest, and the cross from the wordmark's T blown up across the back. One mark, nothing else.",
    details: [...HOODIE_BASE, "Oversized cross across the back"],
    fit: HOODIE_FIT,
    sizeGuide: TOP_GUIDE,
    colours: colourways("cross-zip-hoodie", ["front", "back", "back-detail", "chest-detail"], {
      front: "Cross Zip Hoodie, front: cropped zip hoodie with a white FTD wordmark across the chest and a pouch pocket; plain balloon sleeves.",
      back: "Cross Zip Hoodie, back: a single large white cross, the T from the FTD wordmark, across the middle of the back.",
      "back-detail": "Close-up of the back cross with its flared, wavering edges.",
      "chest-detail": HOODIE_CHEST,
    }),
  },
  {
    slug: "crossbone-baggy-pants",
    name: "Crossbone Baggy Pants",
    price: 110,
    summary:
      "A barrel leg, wide through the knee and curved back in to the hem. Crossbone crosses wrap the side seams at the hip, knee and shin, printed to match the zip hoodie.",
    details: [
      "Heavyweight fleece to match the zip hoodies",
      "Barrel leg, curved from hip to hem",
      "Elasticated waistband with drawcord",
      "Side pockets and a rear welt pocket",
      "Crossbone crosses wrapping both side seams",
    ],
    fit: "Cut wide with a curved leg. Take your usual waist size.",
    sizeGuide: BOTTOM_GUIDE,
    colours: colourways("crossbone-baggy-pants", ["front", "back", "front-detail"], {
      front: "Crossbone Baggy Pants, front: barrel-leg joggers with a drawcord waist and crossbone crosses wrapping round the outer side seams at the hip, knee and shin.",
      back: "Crossbone Baggy Pants, back: rear welt pockets, a clean seat, and the back halves of the crosses wrapping round from the side seams.",
      "front-detail": "Close-up of the crossbone print on the front of the leg, beside the drawcord.",
    }),
  },
];

export const getProduct = (slug) => PRODUCTS.find((p) => p.slug === slug);

export const getColour = (product, id) => product.colours.find((c) => c.id === id) || product.colours[0];

export const formatPrice = (value) =>
  new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(value);
