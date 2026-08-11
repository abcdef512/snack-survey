"""Apply catalog merges and extract product thumbnails from the Gmarket catalog sheets."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageOps


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "public" / "snack-catalog.json"
OUTPUT_DIR = ROOT / "public" / "product-images"
SOURCE_URL = "https://item.gmarket.co.kr/Item?goodsCode=3666435816"

# Each key is the option that remains visible. Values are packaging duplicates
# that are folded into the representative option.
MERGES = {
    90384570058: [90404336255],
    88269087830: [90384570048],
    88269087831: [90384570049],
    88269087833: [90384570047],
    88269087834: [90384570046],
    88269087878: [89694426771, 89910185456],
    88269087879: [90384570070, 89910185457],
    88269087880: [89694426782, 89910185462],
    88269087881: [90355366718],
    88269087882: [90384570069, 89910185458],
    88269087885: [89910185496],
    88269087886: [89910185497],
    88269087887: [89910185495],
    88269087893: [90384570072],
    88269087896: [89910185486],
    88269087897: [89694426779],
    88269087902: [89910185466],
    89694426704: [88269087982],
    89892199014: [89910185465],
    88269087906: [89910185472],
    88269087907: [89910185481],
    88269087923: [89910185470],
    89694426727: [90355366721, 89910185459],
    89694426725: [90384570071, 89910185460],
    89694426729: [89910185464],
    89694426731: [89910185463],
    88269087981: [90384570064, 88269088116],
    90384570066: [89910185511],
    90384570065: [89910185512],
    90355366724: [89694426806],
    90355366725: [89694426804],
    90384570073: [89694426808],
    90384570074: [90384570075],
    90384570079: [90384570082],
    90384570080: [90384570083],
    89919350133: [90443568040],
    89694426984: [89694426951],
    89694426983: [89694426953],
    89879737999: [89694426955],
    89694426987: [89694426986],
    90245098353: [90422522064],
    90245098358: [90422522068],
    90288254940: [90422522067],
    90422522057: [90422522052],
    90422522060: [90422522054],
    90422522062: [90422522053],
    90422522069: [90422522056],
    90422522102: [90422522090],
    90422522100: [90422522092],
    90422522099: [90422522094],
    90422522097: [90422522095],
    89879738003: [88269088262],
    88269087835: [90451429566],
    88269087828: [90451429548],
    90384570045: [90451429553],
    89910185517: [89251796962],
    89910185477: [89910185549],
}

NAME_FIXES = {
    "31_다이재샌드 밀크크림 93g(3개)": "31_다이제샌드 밀크크림 93g(3개)",
    "21_청우 그랑쉘ㅇ사과 195g": "21_청우 그랑쉘 사과 195g",
    "40_에너지바 저당 미니 202.5g5g": "40_에너지바 저당 미니 202.5g",
    "03__크라운 마이쮸 스틱 포도(7개)": "03_크라운 마이쮸 스틱 포도(7개)",
    "28_누룽지팝 매●콤 142g+새우깡 30g": "28_누룽지팝 매콤 142g+새우깡 30g",
    "40_삼림약과 초당옥수수 70g(총4개)": "40_삼립약과 초당옥수수 70g(총4개)",
    "42_삼림약과 오리지널 70g(총4개)": "42_삼립약과 오리지널 70g(총4개)",
    "13_포테이토 샤워크림 15g(36개)": "13_포테이토 사워크림 15g(36개)",
    "24_참그래인우리밀 192g+48g": "24_참그레인 우리밀 192g+48g",
    "13_참그레인우리밀 48g(4개)": "13_참그레인 우리밀 48g(4개)",
    "41_롯데 에이비씨 초코 72g(2개)": "41_롯데 ABC 초콜릿 72g(2개)",
    "42_롯데 에이비씨 초코 187g": "42_롯데 ABC 초콜릿 187g",
}

SOURCE_OPTION_COUNTS = {
    1: 42,
    2: 50,
    3: 50,
    4: 48,
    5: 50,
    6: 46,
    7: 48,
    8: 42,
    9: 42,
    10: 39,
    11: 43,
}

# The seller updated some option lists without replacing the older detail
# sheets. These products still exist in the sheets but at their former slot.
IMAGE_POSITION_OVERRIDES = {
    90451449482: 32,
    90451429545: 18,
    90422521759: 24,
    90422521760: 25,
    90422521762: 26,
    90422521765: 27,
    90422521767: 30,
    90422521769: 31,
    90422521773: 34,
    89879737979: 23,
    89879737980: 24,
    89879737982: 25,
    89879737983: 26,
    89879737984: 27,
    89879737985: 28,
    89879737986: 29,
    89879737988: 30,
    89879737990: 31,
    89879737992: 32,
    89879737994: 33,
    89694426982: 34,
    89694426983: 35,
    89694426984: 36,
    89879737999: 37,
    89694426986: 38,
    89694426987: 39,
    89879738003: 40,
}

# These recently added options do not appear anywhere in the seller's detail
# sheets, so a neutral fallback is safer than showing another product's photo.
NO_SOURCE_IMAGE = {
    90451429546,
    90422521771,
    90422521775,
    90384570101,
    89879737978,
}

# Products that should not appear in the survey at all. They are removed from
# the catalog (rather than merely disabled) and their generated image is also
# deleted.
REMOVE_OPTIONS = {
    # 01.신제품할인: 코피코 묶음 상품
    90451429531,
    90451429532,
    90451429533,
    90451429535,
    90451449482,
    90451429544,
    90451429546,
    # 04.비스켓2: 알로 시리즈
    90384570059,
    90384570060,
    90384570061,
    # 05.비스켓소용량: 뽀로로 시리즈
    89910185474,
    89910185475,
    # 09.초콜릿: 톡핑/드림/크런키볼 묶음
    89879737975,
    89879737976,
    90384570101,
    89879737978,
    89879737990,
    89879737992,
    89879737994,
    # 10.캔디양갱: 마이쮸 복숭아 용기
    90422522051,
    # 11.캔디껌: 오징어/견과 안주류
    90443424112,
    90443424115,
    90443424118,
    90443424122,
    90443424124,
    90443424125,
    90443424127,
    90443424129,
    90443424131,
    90443424133,
    90443424135,
    90443424136,
    90443424137,
    90443424139,
}

# The source page is a stitched product grid. Its rows are not equally tall,
# so using an average row height eventually drifts into the price of the next
# product. These are the real top edges of each product row in the 11 sheets.
ROW_TOPS = {
    1: [312, 705, 1097, 1489, 1881, 2271, 2662, 3054, 3446, 3839, 4230, 4621, 5012, 5402],
    2: [343, 735, 1129, 1523, 1916, 2308, 2699, 3094, 3486, 3879, 4272, 4666, 5058, 5451, 5847, 6239, 6635],
    3: [343, 736, 1129, 1523, 1916, 2308, 2699, 3092, 3486, 3879, 4271, 4664, 5056, 5450, 5841, 6234, 6626],
    4: [340, 732, 1124, 1516, 1907, 2298, 2690, 3082, 3473, 3864, 4256, 4649, 5042, 5436, 5828, 6223],
    5: [336, 728, 1119, 1511, 1909, 2305, 2697, 3091, 3488, 3886, 4278, 4670, 5063, 5457, 5849, 6241, 6633],
    6: [343, 736, 1128, 1520, 1913, 2305, 2699, 3091, 3484, 3881, 4273, 4666, 5060, 5452, 5848, 6241],
    7: [345, 764, 1198, 1620, 2036, 2442, 2853, 3262, 3662, 4056, 4454, 4854, 5253, 5650, 6045, 6437],
    8: [345, 764, 1198, 1620, 2036, 2442, 2855, 3262, 3662, 4056, 4454, 4854, 5255, 5647],
    9: [343, 735, 1127, 1521, 1912, 2303, 2696, 3087, 3480, 3871, 4266, 4660, 5052, 5444],
    10: [343, 735, 1129, 1522, 1914, 2306, 2700, 3092, 3485, 3876, 4268, 4659, 5052],
}

# Sheet 11 inserts a section banner between candy and gum, so its gum rows
# need explicit positions instead of the normal three-items-per-row formula.
CATEGORY_11_ROW_TOPS = [336, 730, 1128, 1520, 1912, 2305, 2699, 3168, 3561, 3955]

CELL_X = [(32, 285), (304, 559), (575, 830)]


def load_source_sheets(manifest_path: Path) -> dict[int, Path]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sheets: dict[int, Path] = {}
    for asset in manifest.get("assets", []):
        match = re.search(r"/(\d{2})\.jpg$", asset.get("url", ""))
        if match:
            sheets[int(match.group(1))] = Path(asset["path"])
    missing = sorted(set(SOURCE_OPTION_COUNTS) - set(sheets))
    if missing:
        raise SystemExit(f"원본 카테고리 이미지가 없습니다: {missing}")
    return sheets


def apply_merges(catalog: dict) -> tuple[int, int]:
    products = catalog["products"]
    by_option = {int(product["optionNo"]): product for product in products}
    expected = set(MERGES) | {alias for aliases in MERGES.values() for alias in aliases}
    missing = sorted(expected - set(by_option))
    if missing:
        raise SystemExit(f"카탈로그에서 옵션 번호를 찾을 수 없습니다: {missing}")

    for product in products:
        product["name"] = NAME_FIXES.get(product["name"], product["name"])
        if str(product["category"]).startswith("11."):
            product["category"] = "11.캔디껌"
        product.pop("mergedInto", None)
        product.pop("mergedOptionNos", None)

    for keep, aliases in MERGES.items():
        representative = by_option[keep]
        representative["optionStatus"] = True
        representative["mergedOptionNos"] = aliases
        for alias in aliases:
            duplicate = by_option[alias]
            duplicate["optionStatus"] = False
            duplicate["mergedInto"] = keep

    products[:] = [
        product for product in products if int(product["optionNo"]) not in REMOVE_OPTIONS
    ]

    active = [product for product in products if product.get("optionStatus")]
    category_counts = Counter(product["category"] for product in active)
    catalog["categories"] = [
        {
            "category": "11.캔디껌" if str(item["category"]).startswith("11.") else item["category"],
            "count": category_counts.get(
                "11.캔디껌" if str(item["category"]).startswith("11.") else item["category"],
                0,
            ),
        }
        for item in catalog["categories"]
    ]

    catalog["extractedCount"] = len(products)
    catalog["activeCount"] = len(active)
    catalog["imageSourceUrl"] = SOURCE_URL
    return len(products), len(active)


def extract_thumbnail(sheet: Image.Image, category: int, option_position: int) -> Image.Image:
    row, column = divmod(option_position - 1, 3)
    row_tops = CATEGORY_11_ROW_TOPS if category == 11 else ROW_TOPS[category]
    if row >= len(row_tops):
        raise ValueError(f"상품 행이 없습니다: category={category}, position={option_position}")

    row_top = row_tops[row]
    row_steps = [right - left for left, right in zip(row_tops, row_tops[1:])]
    typical_step = sorted(row_steps)[len(row_steps) // 2]
    next_top = (
        row_tops[row + 1]
        if row + 1 < len(row_tops)
        else min(sheet.height, row_top + typical_step)
    )
    row_height = next_top - row_top
    left, right = CELL_X[column]
    top = row_top + 9
    bottom = min(round(row_top + row_height * 0.72), sheet.height)
    if bottom <= top:
        raise ValueError(
            f"잘못된 이미지 좌표: category={category}, position={option_position}, "
            f"height={sheet.height}, top={top}, bottom={bottom}"
        )
    cropped = sheet.crop((left, top, right, bottom)).convert("RGB")

    # Normalize the seller grid's near-white background and erase any neutral
    # gray pixels still touching the crop edges. This prevents faint source
    # table lines from appearing at the left or right of the product card.
    pixels = np.asarray(cropped).copy()
    spread = pixels.max(axis=2) - pixels.min(axis=2)
    minimum = pixels.min(axis=2)
    near_white = (minimum >= 230) & (spread <= 18)
    edge_band = np.zeros(near_white.shape, dtype=bool)
    edge_band[:10, :] = True
    edge_band[-10:, :] = True
    edge_band[:, :10] = True
    edge_band[:, -10:] = True
    edge_gray = edge_band & (minimum >= 180) & (spread <= 18)
    pixels[near_white | edge_gray] = 255
    cropped = Image.fromarray(pixels, "RGB")

    # Tighten the white margin around the package so every product sits
    # upright and large in the card, without keeping source-grid borders.
    background = Image.new("RGB", cropped.size, "white")
    difference = ImageOps.grayscale(ImageChops.difference(cropped, background))
    mask = difference.point(lambda value: 255 if value > 12 else 0)

    # Product art forms one dense vertical run. Option badges, descriptions,
    # borders and prices sit below it after a clear white gap; trim that lower
    # source-card metadata before calculating the final bounding box.
    row_counts = (np.asarray(mask) > 0).sum(axis=1).tolist()
    runs: list[list[int]] = []
    for y, pixels in enumerate(row_counts):
        if pixels <= 10:
            continue
        if not runs or y - runs[-1][-1] > 6:
            runs.append([y])
        else:
            runs[-1].append(y)
    product_run = next((run for run in runs if run[-1] - run[0] >= 20), None)
    if product_run:
        cropped = cropped.crop((0, 0, cropped.width, min(cropped.height, product_run[-1] + 6)))
        background = Image.new("RGB", cropped.size, "white")
        difference = ImageOps.grayscale(ImageChops.difference(cropped, background))
        mask = difference.point(lambda value: 255 if value > 12 else 0)

    bbox = mask.getbbox()
    if bbox:
        pad = 8
        cropped = cropped.crop(
            (
                max(0, bbox[0] - pad),
                max(0, bbox[1] - pad),
                min(cropped.width, bbox[2] + pad),
                min(cropped.height, bbox[3] + pad),
            )
        )

    contained = ImageOps.contain(cropped, (300, 280), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (320, 300), "white")
    canvas.paste(contained, ((320 - contained.width) // 2, (300 - contained.height) // 2))

    # A few package photos include a long neutral-gray scan/shadow line just
    # outside the product. Remove only near-neutral columns that span most of
    # the thumbnail; colored package details and text are left untouched.
    canvas_pixels = np.asarray(canvas).copy()
    canvas_spread = canvas_pixels.max(axis=2) - canvas_pixels.min(axis=2)
    canvas_minimum = canvas_pixels.min(axis=2)
    canvas_maximum = canvas_pixels.max(axis=2)
    neutral = (
        (canvas_spread <= 18)
        & (canvas_minimum >= 150)
        & (canvas_maximum <= 250)
    )
    long_line_columns = np.where(neutral.sum(axis=0) >= 220)[0]
    expanded_columns = {
        nearby
        for column in long_line_columns
        for nearby in range(max(0, column - 3), min(canvas.width, column + 4))
    }
    for column in expanded_columns:
        removable = (
            (canvas_spread[:, column] <= 24)
            & (canvas_minimum[:, column] >= 145)
            & (canvas_maximum[:, column] <= 252)
        )
        canvas_pixels[removable, column] = 255
    return Image.fromarray(canvas_pixels, "RGB")


def build_images(catalog: dict, sheets: dict[int, Path]) -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    opened = {category: Image.open(path).convert("RGB") for category, path in sheets.items()}
    positions: dict[int, int] = {}
    category_positions: dict[int, int] = {}
    for product in catalog["products"]:
        category_match = re.match(r"(\d+)\.", str(product["category"]))
        if not category_match:
            raise SystemExit(f"카테고리를 해석할 수 없습니다: {product['category']}")
        category = int(category_match.group(1))
        category_positions[category] = category_positions.get(category, 0) + 1
        prefix = re.match(r"(\d+)_", str(product["name"]))
        positions[int(product["optionNo"])] = (
            int(prefix.group(1)) if prefix else category_positions[category]
        )
    count = 0
    try:
        for product in catalog["products"]:
            option_no = int(product["optionNo"])
            output_path = OUTPUT_DIR / f"{option_no}.webp"
            if not product.get("optionStatus"):
                product.pop("image", None)
                output_path.unlink(missing_ok=True)
                continue

            if option_no in NO_SOURCE_IMAGE:
                if output_path.exists():
                    product["image"] = f"/product-images/{output_path.name}"
                    count += 1
                else:
                    product.pop("image", None)
                continue

            category_match = re.match(r"(\d+)\.", str(product["category"]))
            if not category_match:
                raise SystemExit(f"이미지 위치를 계산할 수 없습니다: {product['name']}")

            category = int(category_match.group(1))
            option_position = IMAGE_POSITION_OVERRIDES.get(option_no, positions[option_no])
            thumbnail = extract_thumbnail(
                opened[category], category, option_position
            )
            filename = f"{option_no}.webp"
            thumbnail.save(OUTPUT_DIR / filename, "WEBP", quality=88, method=6)
            product["image"] = f"/product-images/{filename}"
            count += 1
    finally:
        for sheet in opened.values():
            sheet.close()

    referenced = {
        Path(product["image"]).name
        for product in catalog["products"]
        if product.get("image")
    }
    for output_path in OUTPUT_DIR.glob("*.webp"):
        if output_path.name not in referenced:
            output_path.unlink()
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--asset-manifest",
        required=True,
        type=Path,
        help="Browser page-assets bundle manifest containing 01.jpg through 11.jpg",
    )
    args = parser.parse_args()

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    total, active = apply_merges(catalog)
    image_count = build_images(catalog, load_source_sheets(args.asset_manifest))
    CATALOG_PATH.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"전체 {total}개 중 활성 {active}개, 이미지 {image_count}개 생성")


if __name__ == "__main__":
    main()
