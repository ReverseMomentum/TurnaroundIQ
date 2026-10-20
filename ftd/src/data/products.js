// Drop 01 catalogue. Prices are indicative and every spec here is illustrative
// until the pieces are confirmed for release; the UI labels them that way.

export const DROP = {
  code: "DROP 01",
  status: "unreleased", // "unreleased" | "live" (no checkout is wired yet)
  statusLabel: "Not yet released",
};

export const SIZES = ["XS", "S", "M", "L", "XL", "XXL"];

const img = (name, alt, label) => ({
  src: `/art/${name}.webp`,
  thumb: `/art/${name}-thumb.webp`,
  alt,
  label,
});

export const PRODUCTS = [
  {
    slug: "crossbone-zip-hoodie",
    name: "Crossbone Zip Hoodie",
    price: 120,
    summary:
      "Built for the long haul. Heavyweight construction, an oversized silhouette, and custom crossbone artwork across a washed-black finish. Made to be worn hard and kept longer.",
    details: [
      "Heavyweight brushed-back fleece",
      "Oversized, slightly cropped fit with dropped shoulders",
      "Full-length two-way zip",
      "FTD wordmark across the chest",
      "Crossbone artwork across both sleeves and the back",
      "Ribbed cuffs and hem",
    ],
    fit: "Cut oversized. Take your usual size for the intended drape, or size down for a closer fit.",
    images: [
      img("hoodie-front", "Crossbone Zip Hoodie, front: washed-black zip hoodie with a white blackletter FTD wordmark across the chest and crossbone prints down each sleeve.", "Front"),
      img("hoodie-back", "Crossbone Zip Hoodie, back: a large white crossbone cross printed across the back, with a small FTD mark beneath the hood.", "Back"),
      img("hoodie-detail-sleeve", "Close-up of the sleeve print: a gothic cross over crossed femurs, worn into the fabric.", "Sleeve detail"),
      img("hoodie-detail-chest", "Close-up of the chest wordmark split by the zip, with drawcords and metal tips.", "Chest detail"),
    ],
  },
  {
    slug: "crossbone-baggy-pants",
    name: "Crossbone Baggy Pants",
    price: 110,
    summary:
      "Wide through the leg and stacked at the ankle. Crossbone artwork runs the length of both legs, printed to match the zip hoodie.",
    details: [
      "Heavyweight fleece to match the zip hoodie",
      "Relaxed, wide leg",
      "Elasticated waist with drawcord",
      "Ribbed ankle cuffs",
      "Crossbone artwork down both legs",
    ],
    fit: "Cut wide. Take your usual waist size.",
    images: [
      img("pants", "Crossbone Baggy Pants: washed-black wide-leg joggers with three crossbone prints down each leg.", "Front"),
    ],
  },
  {
    slug: "heaven-graphic-tee",
    name: "Heaven Graphic Tee",
    price: 70,
    summary:
      "Blackletter HEAVEN over a thorned halo, printed across the chest of a boxy, heavyweight tee. You can't run from it.",
    details: [
      "Heavyweight cotton jersey",
      "Boxy fit, dropped shoulder",
      "Ribbed crew neck",
      "Front print: HEAVEN with halo and crossbone",
    ],
    fit: "Boxy. Take your usual size.",
    images: [
      img("tee-heaven", "Heaven Graphic Tee: washed-black tee printed with blackletter Heaven above a thorned halo and a small crossbone.", "Front"),
    ],
  },
  {
    slug: "decay-tee",
    name: "Decay Tee",
    price: 65,
    summary:
      "A thorn-wrapped blade runs from collar to hem. The FTD mark above, NOTHING LASTS below. A heavyweight tee for heavy days.",
    details: [
      "Heavyweight cotton jersey",
      "Boxy fit, dropped shoulder",
      "Ribbed crew neck",
      "Full-length front print",
    ],
    fit: "Boxy. Take your usual size.",
    images: [
      img("tee-decay", "Decay Tee: washed-black tee with a full-length thorn-wrapped sword print and the FTD wordmark at the chest.", "Front"),
    ],
  },
];

export const getProduct = (slug) => PRODUCTS.find((p) => p.slug === slug);

export const formatPrice = (value) =>
  new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(value);

// Indicative garment measurements in centimetres, flat across. Published for
// planning only: final grading is confirmed at release.
export const SIZE_GUIDE = {
  columns: ["Size", "Chest", "Length", "Sleeve"],
  rows: [
    ["XS", 60, 62, 58],
    ["S", 63, 64, 60],
    ["M", 66, 66, 62],
    ["L", 69, 68, 63],
    ["XL", 72, 70, 64],
    ["XXL", 75, 72, 65],
  ],
};
