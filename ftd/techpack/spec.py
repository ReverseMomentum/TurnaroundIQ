"""Tech pack data for the Drop 01 samples. Edit here, then rebuild:

    python3 scripts/build_techpack.py

Status of every value: "CONFIRMED" (decided by FTD), "PROPOSED" (a starting
point from the flats and typical specs for this garment type; confirm or change),
or "TBC" (needs an answer, usually from the manufacturer).
Measurements are centimetres, garment laid flat (half measurements) unless noted.
"""

VERSION = "v0.1"
DATE = "21 Oct 2026"
SAMPLE_SIZE = "M"
SIZES = ["XS", "S", "M", "L", "XL", "XXL"]
BRAND = {
    "name": "FTD — Forsaken To Decay",
    "contact": "",  # name / email / phone, filled in before sending
    "address": "",
}

# ---------------------------------------------------------------- hoodie block

# Scale used to size prints from the flats: the proposed 66 cm chest = 590 px.
HOODIE_CM_PER_PX = 66 / 590
PANTS_CM_PER_PX = 58 / 323  # proposed 58 cm hip = 323 px

HOODIE_POM = [
    # code, point of measure, how to measure, M value, grade per size, tolerance
    ("A", "Body length", "HPS to bottom edge of hem rib", 60, 2, 1),
    ("B", "Chest width", "2.5 cm below armhole, edge to edge", 66, 3, 1),
    ("C", "Shoulder width (dropped)", "Shoulder seam point to point, across back", 64, 3, 1),
    ("D", "Body width above hem rib", "Edge to edge at the rib seam", 52, 3, 1),
    ("E", "Hem rib width, relaxed", "Bottom edge, edge to edge", 40, 3, 1),
    ("F", "Hem rib height", "Rib seam to bottom edge", 7, 0, 0.5),
    ("G", "Armhole, straight", "Shoulder point to underarm, straight", 30, 1, 0.5),
    ("H", "Sleeve length", "Shoulder seam to cuff edge, along top of sleeve", 60, 1, 1),
    ("I", "Bicep width", "2.5 cm below armhole, perpendicular to sleeve", 29, 1, 0.5),
    ("J", "Sleeve width at balloon", "Widest point of lower sleeve, approx. 20 cm above cuff", 31, 1, 0.5),
    ("K", "Cuff width, relaxed", "Cuff edge, edge to edge", 9.5, 0.5, 0.5),
    ("L", "Cuff height", "Cuff seam to edge", 7, 0, 0.5),
    ("M", "Neck width", "Seam to seam at shoulder", 21, 0.5, 0.5),
    ("N", "Front neck drop", "HPS to top of zip, vertical", 9, 0.5, 0.5),
    ("O", "Hood height", "Neck seam at side to top of hood", 36, 0.5, 1),
    ("P", "Hood width", "Widest point, laid flat", 27, 0.5, 0.5),
    ("Q", "Zip length", "Top stop to bottom of hem rib (to fit)", 52, 1.5, 0.5),
    ("R", "Pouch pocket opening", "Each side, along the opening edge", 16, 0.5, 0.5),
]

HOODIE_FEATURES = [
    "Cropped, boxy body with dropped shoulders and a blouson hem (body gathered into rib)",
    "Full balloon sleeves gathered into ribbed cuffs",
    "Two-piece hood with centre seam, self-lined",
    "Full-length front zip, single slider",
    "Split kangaroo pouch pocket, divided by the zip",
    "Ribbed cuffs and hem",
    "Screen prints by the manufacturer on cut panels before sewing (see artwork pages)",
]

# component, specification, placement, colour, status
HOODIE_BOM = [
    ("Main fabric", "100% cotton heavyweight fleece, brushed back, 450–500 gsm. Pre-shrunk; shrinkage ≤3% length and width. Cotton face required for screen printing (no polyester: ink dye migration).", "Body, sleeves, hood, pocket", "Black", "PROPOSED"),
    ("Hood lining", "Self fabric (double-layer hood)", "Hood", "Black", "PROPOSED"),
    ("Rib", "2×2 rib, 95% cotton / 5% elastane, approx. 400 gsm", "Cuffs, hem", "Black, matched to main", "PROPOSED"),
    ("Zip (sample)", "Metal, open-end (separating), no. 5 or 8 teeth, single auto-lock slider. Best available stock zip in this finish.", "Centre front", "Gunmetal / black nickel", "PROPOSED"),
    ("Zip (production)", "As above with custom FTD puller. Quote separately: mould cost and minimum order.", "Centre front", "TBC", "TBC"),
    ("Thread", "Polyester core-spun, Tex 40", "All seams", "Black", "PROPOSED"),
    ("Neck tape", "Woven or printed tape covering back neck seam (as drawn in flat)", "Inside back neck", "Black", "TBC"),
    ("Main label", "Damask woven, end-fold, 50 × 20 mm visible. Artwork FTD-LBL-02", "Inside CB neck, sewn onto neck tape", "Bone thread on black", "PROPOSED"),
    ("Size label", "Printed satin tab, folded, 15 × 12.5 mm. Artwork FTD-LBL-04", "Under main label", "White on black", "PROPOSED"),
    ("Care / composition label", "Printed satin, 30 × 80 mm. Artwork FTD-LBL-03_care_hoodies", "Left side seam, 8 cm above hem", "White on black", "PROPOSED"),
    ("Flag label (optional)", "Damask woven loop, 15 × 15 mm folded. Artwork FTD-LBL-05", "Left hem rib seam", "Bone thread on black", "PROPOSED"),
]

HOODIE_CONSTRUCTION = [
    ("Seams", "Overlock (4-thread) all body and sleeve seams; twin-needle topstitch 6 mm at armhole seams as drawn."),
    ("Shoulders", "Dropped shoulder; armhole seam topstitched on body side."),
    ("Sleeves", "Balloon shape: extra volume in the lower sleeve, gathered evenly into the cuff. Cuff joined with overlock, topstitched."),
    ("Hem", "Body gathered evenly into rib hem (blouson). Rib joined with overlock, cover-stitched."),
    ("Zip", "Inserted between front panels, ending at hem rib bottom and at neck. Topstitched both sides 3 mm. Zip teeth exposed as drawn."),
    ("Hood", "Two-piece, centre seam. Self-lined, joined at face opening and neck; no drawcord (per flat, confirm)."),
    ("Pouch pocket", "Split pouch, one each side of zip; opening edges bound or topstitched 6 mm; bar-tack at opening ends."),
    ("Neck", "Back neck seam covered with neck tape; main label sewn into tape at centre back."),
    ("Finishing", "Trim all threads; press; no fusing. Fold and bag individually."),
]

# ---------------------------------------------------------------- pants block

PANTS_POM = [
    ("A", "Waist, relaxed", "Top edge of waistband, edge to edge", 36, 3, 1),
    ("B", "Waist, extended", "Top edge, fully stretched", 52, 3, 1),
    ("C", "Hip", "18 cm below top of waistband, edge to edge", 58, 3, 1),
    ("D", "Front rise", "Top of waistband to crotch seam, including band", 33, 1, 0.5),
    ("E", "Back rise", "Top of waistband to crotch seam, including band", 42, 1, 0.5),
    ("F", "Thigh", "2.5 cm below crotch, perpendicular to leg", 36, 1.5, 0.5),
    ("G", "Knee (barrel peak)", "36 cm below crotch", 37, 1.5, 0.5),
    ("H", "Leg opening", "Hem edge, edge to edge", 25, 1, 0.5),
    ("I", "Inseam", "Crotch to hem edge", 76, 1, 1),
    ("J", "Outseam", "Top of waistband to hem edge, along the curved side", 108, 1.5, 1),
    ("K", "Waistband height (both bands)", "Top edge to lower band seam", 9, 0, 0.5),
    ("L", "Side pocket opening", "Along the opening edge", 16, 0.5, 0.5),
    ("M", "Rear welt pocket width", "Each pocket, end to end", 13, 0.5, 0.5),
]

PANTS_FEATURES = [
    "Barrel leg: wide through the knee, curving back in to the hem",
    "Stacked double waistband, elasticated, with drawcord exiting at centre front",
    "Slanted side pockets",
    "Two rear welt pockets",
    "Centre back seam",
    "Clean-finished hem",
    "Screen prints by the manufacturer on cut panels before sewing (see artwork pages)",
]

PANTS_BOM = [
    ("Main fabric", "Same fleece as the zip hoodies: 100% cotton, brushed back, 450–500 gsm, pre-shrunk ≤3%", "Legs, waistband", "Black", "PROPOSED"),
    ("Elastic", "Knitted elastic, 40 mm", "Inside upper waistband", "Black", "PROPOSED"),
    ("Drawcord", "Round cotton cord, 8 mm, approx. 140 cm; tips TBC (knotted or metal aglets)", "Lower waistband channel, exits at CF", "Black", "PROPOSED"),
    ("Drawcord exits", "Two buttonholes or gunmetal metal eyelets", "CF lower waistband", "Black / gunmetal", "TBC"),
    ("Pocketing", "Self fabric or black cotton jersey", "Side and rear pocket bags", "Black", "PROPOSED"),
    ("Thread", "Polyester core-spun, Tex 40", "All seams", "Black", "PROPOSED"),
    ("Main label", "Damask woven, end-fold, same as hoodies. Artwork FTD-LBL-02", "Inside CB waistband", "Bone thread on black", "PROPOSED"),
    ("Size label", "Printed satin tab, folded. Artwork FTD-LBL-04", "Under main label", "White on black", "PROPOSED"),
    ("Care / composition label", "Printed satin, 30 × 80 mm. Artwork FTD-LBL-03_care_joggers", "Inside left side seam, below waistband", "White on black", "PROPOSED"),
    ("Flag label (optional)", "Damask woven loop. Artwork FTD-LBL-05", "Right hip seam", "Bone thread on black", "PROPOSED"),
]

PANTS_CONSTRUCTION = [
    ("Seams", "Overlock (4-thread); topstitch as drawn at pockets and waistband."),
    ("Barrel leg", "Curved outseam and inseam to create the barrel. Manufacturer to advise if knee darts or a shaped front panel are needed to hold the curve."),
    ("Waistband", "Stacked double band. Upper band carries the 40 mm elastic; lower band carries the drawcord channel with exits at CF. Both bands topstitched as drawn."),
    ("Side pockets", "Slanted opening, topstitched 6 mm, bar-tacked at both ends."),
    ("Rear welts", "Two single-welt pockets, bar-tacked. Sewn after printing (the back print crosses the right welt)."),
    ("Centre back", "Centre back seam, overlocked and topstitched."),
    ("Hem", "Turned and twin-needle stitched, 2.5 cm, as drawn."),
    ("Finishing", "Trim all threads; press; fold and bag individually."),
]

# ---------------------------------------------------------------- styles

PRINT_METHOD = ("Screen print by the manufacturer (in house or their usual print partner), one colour, white. "
                "Ink: water-based discharge or white plastisol, please advise for this fabric; strike-off on "
                "sample fabric to be approved by FTD before the sample panels are printed.")

# Print artwork: three one-colour pieces cover all of Drop 01. Files in techpack/artwork/
# are built by scripts/build_print_files.py (vector SVG + 300 dpi film positive, black = ink).
# The same cross artwork is used at one size everywhere, so one screen serves both garments.
ARTWORK = {
    "ART-01": dict(name="FTD wordmark", file="FTD-ART-01_FTD-wordmark", size="45 × 22.3",
                   used="HD01 chest, HD02 chest", status="PROPOSED"),
    "ART-02": dict(name="NEVER ENOUGH logo", file="FTD-ART-02_Never-Enough", size="50 × 45.9",
                   used="HD02 back", status="PROPOSED",
                   note="At the limit of a standard screen; confirm the printer's maximum print area."),
    "ART-03": dict(name="Crossbone cross", file="FTD-ART-03_Crossbone-cross", size="30 × 37.3",
                   used="HD01 back ×2, sleeves ×2; PT01 legs ×4", status="PROPOSED",
                   note="One screen, rotated per placement. Where a cross runs off a panel edge it is printed full size and cut by the seam."),
}

STYLES = [
    {
        "code": "FTD-D01-HD01",
        "why": "The FTD wordmark crosses the zip, the back crosses run over the shoulder seams onto the sleeves, and the sleeve crosses wrap a gathered balloon sleeve. None of these can be printed cleanly once the garment is sewn.",
        "slug": "crossbone-zip-hoodie",
        "name": "Crossbone Zip Hoodie",
        "block": "hoodie",
        "colour": "Black",
        "summary": "Cropped boxy zip hoodie with balloon sleeves. FTD wordmark on the chest, crossbone crosses down both sleeves and across the back shoulders.",
        "prints": [
            # name, approx size w x h (cm), placement, panels printed
            ("P1  FTD wordmark (ART-01)", "45 × 22.3", "Centred on CF, across the zip. Top edge approx. 8 cm below HPS. Matched across the zip within 3 mm.", "Front L, Front R"),
            ("P2  Back crosses ×2 (ART-03)", "30 × 37.3 each", "Diagonal across upper back, rotated as drawn. Both run over the shoulder seams onto the sleeves; match at the seams within 5 mm.", "Back, Sleeve L, Sleeve R"),
            ("P3  Sleeve crosses ×2 (ART-03)", "30 × 37.3 each", "One per sleeve, rotated as drawn, wrapping from front to back. Printed on the flat sleeve panel.", "Sleeve L, Sleeve R"),
        ],
        "artwork": ["ART-01", "ART-03"],
        "printed_panels": ["Front L", "Front R", "Back", "Sleeve L", "Sleeve R"],
        "factory_panels": ["Hood (×2 outer, ×2 lining)", "Pouch pocket pieces", "Cuff rib (×2)", "Hem rib"],
    },
    {
        "code": "FTD-D01-HD02",
        "why": "The FTD wordmark crosses the zip, so the two front panels are printed before the zip goes in. The back is printed flat at the same time so all prints are cured together.",
        "slug": "never-enough-zip-hoodie",
        "name": "Never Enough Zip Hoodie",
        "block": "hoodie",
        "colour": "Black",
        "summary": "Same body as HD01. FTD wordmark on the chest, NEVER ENOUGH death-metal logo across the back. Plain sleeves.",
        "prints": [
            ("P1  FTD wordmark (ART-01)", "45 × 22.3", "Centred on CF, across the zip. Top edge approx. 8 cm below HPS. Matched across the zip within 3 mm.", "Front L, Front R"),
            ("P2  NEVER ENOUGH logo (ART-02)", "50 × 45.9", "Centred on CB. Top edge approx. 2 cm below the hood seam.", "Back"),
        ],
        "artwork": ["ART-01", "ART-02"],
        "printed_panels": ["Front L", "Front R", "Back"],
        "factory_panels": ["Sleeves (×2)", "Hood (×2 outer, ×2 lining)", "Pouch pocket pieces", "Cuff rib (×2)", "Hem rib"],
    },
    {
        "code": "FTD-D01-PT01",
        "why": "The crosses run off the side seams, across the centre back seam and over the right rear welt pocket. The legs are printed flat before the seams, welts and waistband are sewn.",
        "slug": "crossbone-baggy-pants",
        "name": "Crossbone Baggy Pants",
        "block": "pants",
        "colour": "Black",
        "summary": "Barrel-leg fleece pants with a stacked drawcord waistband. Crossbone crosses across both legs, front and back.",
        "prints": [
            ("P1  Front cross, left leg (ART-03)", "30 × 37.3", "Upper left leg, rotated as drawn, running off the outseam and cut by the side seam.", "Front L"),
            ("P2  Front cross, right leg (ART-03)", "30 × 37.3", "Lower right leg, rotated as drawn, running off the outseam.", "Front R"),
            ("P3  Back crosses ×2 (ART-03)", "30 × 37.3 each", "Upper back crossing the CB seam and the right welt pocket; second cross lower on the left leg. Match across CB seam within 5 mm.", "Back L, Back R"),
        ],
        "artwork": ["ART-03"],
        "printed_panels": ["Front L", "Front R", "Back L", "Back R"],
        "factory_panels": ["Waistband bands", "Pocket bags and facings", "Welt pieces"],
    },
]

QUESTIONS = [
    "Sample cost per style, lead time, and how many fit rounds are included.",
    "Do you screen print in house? If not, who prints, and is printing cut panels before sewing standard for you?",
    "Screen set-up cost per screen and print cost per location. Drop 01 uses three screens (ART-01, -02, -03), shared across styles.",
    "Ink you recommend on this fleece (discharge or plastisol), and the cost of a strike-off on our fabric.",
    "Production minimum order per style and colour, and how it can be split across sizes.",
    "Fleece options at 450–500 gsm, 100% cotton: shrinkage figures and colourfastness.",
    "Zip options for the sample (brand, finish), and for production: cost and minimum for a custom puller, including mould fee.",
    "Can you grade the pattern XS–XXL? Who owns the pattern, and can we have a copy (PDF or DXF)?",
    "Can you source the woven main and size labels, and the care labels?",
    "Shipping method, cost and duties to the UK.",
]

LABEL_NOTES = [
    "UK law requires a fibre composition label on clothing sold in the UK (e.g. \"100% cotton\"). Care symbols are standard practice.",
    "Include the brand name and a contact address on the label or packaging so the product can be traced.",
    "Label artwork is in techpack/labels/ (see FTD-labels-overview.pdf). Please quote the woven and printed labels, or advise your usual label supplier.",
]
