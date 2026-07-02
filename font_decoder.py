"""
番茄小说字体加密解码器

混合匹配方案：
1. 字形轮廓 BBox 特征粗过滤（面积、宽高比）
2. 像素渲染精匹配（Top-K 候选者 + 投影轮廓辅助）
3. 定向消歧：已知的罕见字匹配自动回退到高频字库重新匹配
"""
import re
from io import BytesIO
from typing import Dict, Optional

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen

# ==================== 全局缓存 ====================
_ref_data = None
_font_cache: Dict[str, Dict[int, str]] = {}

RENDER_SIZE = 80
MAX_REF_CHARS = 15000  # 参考字符集上限（覆盖更全的 CJK）

# 已知的罕见/错误匹配合集（PUA → 它应映射的高频字）
KNOWN_FIXES = {
    0xE3EE: "然",  # 之前 -> 洑/件, 应 -> 然
    0xE3EF: "长",  # 之前 -> 壱, 应 -> 长
    0xE3F1: "入",  # 之前 -> 丬, 应 -> 入
    0xE3F2: "要",  # 之前 -> 婯, 应 -> 要
    0xE3F4: "一",  # 之前 -> "/"等, 应 -> 一
    0xE3F7: "一",  # 之前 -> 巜, 应 -> 一
    0xE3F9: "还",  # 之前 -> 江, 应 -> 还
    0xE3FA: "个",  # 之前 -> 标点, 应 -> 个
    0xE3FB: "观",  # 之前 -> 坝, 应 -> 观
    0xE401: "象",  # 之前 -> 彖, 应 -> 象
    0xE405: "战",  # 之前 -> 敁, 应 -> 战
    0xE407: "相",  # 之前 -> 枂, 应 -> 相
    0xE409: "界",  # 之前 -> 旲, 应 -> 界
    0xE40A: "黄",  # 之前 -> 宣, 应 -> 黄
    0xE40B: "关",  # 之前 -> 失, 应 -> 关
    0xE427: "全",  # 之前 -> 仝, 应 -> 全
    0xE42D: "很",  # 之前 -> 亻, 应 -> 很
}

# ==================== 硬编码字符集（rainyautumn1/FanqieNovelDownloader） ====================
# 覆盖 PUA 范围 0xE3E8-0xE55B（58344-58715），共 372 个 PUA 编码点
# 来源：https://github.com/rainyautumn1/FanqieNovelDownloader
# 基于番茄小说混淆映射研究，作为视觉匹配的优先备选（无需字体下载、无运行时开销）
_FANQIE_CHARSET_START = 58344
_FANQIE_CHARSET_RAW = [
    'D', '在', '主', '特', '家', '军', '然', '表', '场', '4', '要', '只', 'v', '和', '?', '6', '别', '还', 'g',
    '现', '儿', '岁', '?', '?', '此', '象', '月', '3', '出', '战', '工', '相', 'o', '男', '直', '失', '世', 'F',
    '都', '平', '文', '什', 'V', 'O', '将', '真', 'T', '那', '当', '?', '会', '立', '些', 'u', '是', '十', '张',
    '学', '气', '大', '爱', '两', '命', '全', '后', '东', '性', '通', '被', '1', '它', '乐', '接', '而', '感',
    '车', '山', '公', '了', '常', '以', '何', '可', '话', '先', 'p', 'i', '叫', '轻', 'M', '士', 'w', '着', '变',
    '尔', '快', 'l', '个', '说', '少', '色', '里', '安', '花', '远', '7', '难', '师', '放', 't', '报', '认',
    '面', '道', 'S', '?', '克', '地', '度', 'I', '好', '机', 'U', '民', '写', '把', '万', '同', '水', '新', '没',
    '书', '电', '吃', '像', '斯', '5', '为', 'y', '白', '几', '日', '教', '看', '但', '第', '加', '候', '作',
    '上', '拉', '住', '有', '法', 'r', '事', '应', '位', '利', '你', '声', '身', '国', '问', '马', '女', '他',
    'Y', '比', '父', 'x', 'A', 'H', 'N', 's', 'X', '边', '美', '对', '所', '金', '活', '回', '意', '到', 'z',
    '从', 'j', '知', '又', '内', '因', '点', 'Q', '三', '定', '8', 'R', 'b', '正', '或', '夫', '向', '德', '听',
    '更', '?', '得', '告', '并', '本', 'q', '过', '记', 'L', '让', '打', 'f', '人', '就', '者', '去', '原', '满',
    '体', '做', '经', 'K', '走', '如', '孩', 'c', 'G', '给', '使', '物', '?', '最', '笑', '部', '?', '员', '等',
    '受', 'k', '行', '一', '条', '果', '动', '光', '门', '头', '见', '往', '自', '解', '成', '处', '天', '能',
    '于', '名', '其', '发', '总', '母', '的', '死', '手', '入', '路', '进', '心', '来', 'h', '时', '力', '多',
    '开', '己', '许', 'd', '至', '由', '很', '界', 'n', '小', '与', 'Z', '想', '代', '么', '分', '生', '口',
    '再', '妈', '望', '次', '西', '风', '种', '带', 'J', '?', '实', '情', '才', '这', '?', 'E', '我', '神', '格',
    '长', '觉', '间', '年', '眼', '无', '不', '亲', '关', '结', '0', '友', '信', '下', '却', '重', '己', '老',
    '2', '音', '字', 'm', '呢', '明', '之', '前', '高', 'P', 'B', '目', '太', 'e', '9', '起', '稜', '她', '也',
    'W', '用', '方', '子', '英', '每', '理', '便', '西', '数', '期', '中', 'C', '外', '样', 'a', '海', '们', '任',
]
# 构建查找字典（跳过 '?' 表示不明确的映射）
_FANQIE_HARDCODED_CHARSET: Dict[int, str] = {}
for _i, _ch in enumerate(_FANQIE_CHARSET_RAW):
    if _ch != '?':
        _FANQIE_HARDCODED_CHARSET[_FANQIE_CHARSET_START + _i] = _ch

print(f"[font_decoder] 加载 {len(_FANQIE_HARDCODED_CHARSET)} 个硬编码字符映射")

# 高频汉字（用于消歧）
HIGH_FREQ_CHARS = "的一是不了人我在有他这之大小们个中上国地到大时会" \
    "说就子可要对发自为能下过心也年生看多家如得道天然学" \
    "成工开者手其发好面去她出得以相后里只儿等里与但些那" \
    "于日长又此还没入给并很知多己全些关点确各重将入因正" \
    "名己由部些加至利身次位度海吃回老光门前她其更老好" \
    "战无已很把被让看没又都从什变回果定实定走几两同如高" \
    "外间当起最明所今定见头物来安世通令体合几意接其真情" \
    "新第队听总常立接金或望平其白应西但任做代向原路色关" \
    "数内使间像意你吧气改东信四则至军十务三力次万花之线" \
    "山本五员斯何话少文么解低世受问且共样门别先月水干口" \
    "活住叫种员形边算较根争又教件该论品边已化受传节风正较" \
    "土场八处立备空思总必权须证各科段管取际七需调治组称" \
    "示整程具海维南广办议且斗交放资英运观划吃步拉绝技议" \
    "导组据志清术精状确任集消参照商速九至党团统领造马期" \
    "该调千元士千众资王言式华投持送早号青非党团流影功研" \
    "院银识历转规市专律容易容科指史厂便属专量示示属专指" \
    "界层京响感批志华研取拉铁值消施验半江般底院县革际孔" \
    "倒影落型圆注够节识念除精值省坚势厂联办属武效升转季" \
    "率评副专危急严春稳排技座负承环科责即北南断复升规渐" \
    "站江印乡村协保断省研选族百减检验火黄板况存深响况列" \
    "岛构费收段菜序损导洲推角飞护植精编毒借仍侵倒吨雨升" \
    "浪墙补传累曾肩终遇基严础该况废户害松射香背狠朗帝秒" \
    "幸艺迷超汗待寒封福暴虚靠印欧船静版助述端优桥码构梦" \
    "堆岛潮惊胸潮纵瓶塞印欧船静版助述端优桥码构窗顶堆岛" \
    "潮惊胸潮纵瓶塞窗顶撑盖跨猜默斑瞬狠僵嚷缠茫憋拢柄焰" \
    "紧刚才杀击伤亡绝抓互拿神救答应闻提增份求原继续止" \
    "消算否简谈值半完甚"

# 定向修正列表（这些字符如果在首次匹配中出现了，需要二次检查）
SUSPICIOUS_RARE = set("洑壱婯巜彖丬仝亻〃〒」〸")


# ==================== BBox 特征提取 ====================

def _get_glyph_bounds(font_obj, glyph_name: str):
    try:
        glyph_set = font_obj.getGlyphSet()
        if glyph_name in glyph_set:
            pen = BoundsPen(glyph_set)
            glyph_set[glyph_name].draw(pen)
            return pen.bounds
    except Exception:
        pass
    return None


def _bbox_features(bounds: tuple) -> np.ndarray:
    if bounds is None:
        return np.array([0, 0, 0, 0], dtype=np.float32)
    w = bounds[2] - bounds[0]
    h = bounds[3] - bounds[1]
    area = w * h
    aspect = (w + 1) / (h + 1) if h > 0 else 1.0
    return np.array([w, h, area, aspect], dtype=np.float32)


# ==================== 参考字符集加载 ====================

def _load_reference():
    global _ref_data
    if _ref_data is not None:
        return

    pf_tt = TTFont("/System/Library/Fonts/PingFang.ttc", fontNumber=0)
    pf_cmap = pf_tt.getBestCmap()
    pf_glyph_order = pf_tt.getGlyphOrder()

    pf_unicode_to_glyph = {}
    for cp, glyph_id in pf_cmap.items():
        if isinstance(glyph_id, str):
            pf_unicode_to_glyph[cp] = glyph_id
        elif isinstance(glyph_id, int) and glyph_id < len(pf_glyph_order):
            pf_unicode_to_glyph[cp] = pf_glyph_order[glyph_id]

    ref_cps = []
    for cp in pf_unicode_to_glyph:
        if 0x4E00 <= cp <= 0x9FFF:
            ref_cps.append(cp)
        elif 0x3000 <= cp <= 0x303F:
            ref_cps.append(cp)
        elif 0xFF00 <= cp <= 0xFFEF:
            ref_cps.append(cp)

    ref_cps = sorted(ref_cps)[:MAX_REF_CHARS]

    ref_bboxes = []
    ref_chars = []
    for cp in ref_cps:
        ch = chr(cp)
        gname = pf_unicode_to_glyph.get(cp, "")
        bounds = _get_glyph_bounds(pf_tt, gname)
        bf = _bbox_features(bounds)
        ref_bboxes.append(bf)
        ref_chars.append(ch)

    pf_tt.close()

    ref_font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", RENDER_SIZE, index=0)
    ref_imgs = []
    ref_inks = []
    for ch in ref_chars:
        arr, ink, _ = _render_char(ref_font, ch)
        ref_imgs.append(arr)
        ref_inks.append(ink)

    _ref_data = {
        "imgs": np.array(ref_imgs, dtype=np.float32),
        "inks": np.array(ref_inks, dtype=np.float32),
        "bboxes": np.array(ref_bboxes, dtype=np.float32),
        "chars": ref_chars,
    }
    print(f"[font_decoder] 加载 {len(ref_chars)} 个参考字符")


def _render_char(font, char: str):
    img = Image.new('L', (RENDER_SIZE, RENDER_SIZE), 255)
    draw = ImageDraw.Draw(img)
    try:
        bbox = draw.textbbox((0, 0), char, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (RENDER_SIZE - w) // 2 - bbox[0]
        y = (RENDER_SIZE - h) // 2 - bbox[1]
        draw.text((x, y), char, font=font, fill=0)
        aspect = (w + 1) / (h + 1) if h > 0 else 1.0
    except Exception:
        aspect = 1.0
    arr = np.array(img, dtype=np.float32)
    ink = float(np.sum(arr < 200)) / (RENDER_SIZE * RENDER_SIZE)
    return arr, ink, aspect


# ==================== PUA 特征提取 ====================

def _extract_pua_features(font_tt_path: str, pua_cps: list) -> dict:
    pf_tt = TTFont(font_tt_path)
    cmap = pf_tt.getBestCmap()
    pua_bboxes = {}
    for cp in pua_cps:
        gname = cmap.get(cp, "")
        bounds = _get_glyph_bounds(pf_tt, gname)
        pua_bboxes[cp] = _bbox_features(bounds)
    pf_tt.close()

    fanqie_font = ImageFont.truetype(font_tt_path, RENDER_SIZE)
    pua_pixels = {}
    for cp in pua_cps:
        arr, ink, _ = _render_char(fanqie_font, chr(cp))
        pua_pixels[cp] = {"img": arr, "ink": ink}
    return {"bboxes": pua_bboxes, "pixels": pua_pixels}


# ==================== 匹配算法 ====================

def _quick_score_ref(pua_img, pua_ink, ref_img):
    """快速像素差异评分"""
    pd = float(np.sum(np.abs(ref_img - pua_img))) / (RENDER_SIZE * RENDER_SIZE * 255.0)
    return pd


def _detailed_score(pua_img, pua_ink, ref_img, ref_ink):
    """综合评分：像素 + 投影轮廓 + 墨量"""
    pd = float(np.sum(np.abs(ref_img - pua_img))) / (RENDER_SIZE * RENDER_SIZE * 255.0)
    rh = np.sum(ref_img < 200, axis=1) / RENDER_SIZE
    rv = np.sum(ref_img < 200, axis=0) / RENDER_SIZE
    pua_h = np.sum(pua_img < 200, axis=1) / RENDER_SIZE
    pua_v = np.sum(pua_img < 200, axis=0) / RENDER_SIZE
    hd = float(np.sum(np.abs(rh - pua_h))) / RENDER_SIZE
    vd = float(np.sum(np.abs(rv - pua_v))) / RENDER_SIZE
    prd = (hd + vd) / 2
    return 0.55 * pd + 0.25 * prd + 0.20 * abs(ref_ink - pua_ink)


def _find_best_match(pua_img, pua_ink, pua_bf, candidates_data):
    """在候选列表中找最佳匹配"""
    cand_imgs, cand_inks, cand_chars = candidates_data
    n = len(cand_chars)
    if n == 0:
        return None, 999.0

    # 向量化像素差异
    pua_broadcast = pua_img[np.newaxis, :, :]
    pixel_diffs = np.sum(np.abs(cand_imgs - pua_broadcast), axis=(1, 2))
    pixel_diffs = pixel_diffs / (RENDER_SIZE * RENDER_SIZE * 255.0)

    top_k = min(20, n)
    top_idx = np.argsort(pixel_diffs)[:top_k]

    best_score = 999.0
    best_char = None
    for idx in top_idx:
        score = _detailed_score(pua_img, pua_ink, cand_imgs[idx], cand_inks[idx])
        if score < best_score:
            best_score = score
            best_char = cand_chars[idx]
            if score < 0.04:
                break
    return best_char, best_score


def _filter_candidates(pua_bf, pua_ink, ref_imgs, ref_inks, ref_bboxes, ref_chars):
    """BBox + 墨量过滤，返回候选者的数据元组"""
    pua_area = max(float(pua_bf[2]), 1)
    ref_area = np.maximum(ref_bboxes[:, 2].copy(), 1)
    area_ratio = np.minimum(ref_area, pua_area) / np.maximum(ref_area, pua_area)
    area_mask = area_ratio > 0.7
    asp_diff = np.abs(ref_bboxes[:, 3] - pua_bf[3])
    asp_mask = asp_diff < 0.25
    candidates = np.where(area_mask & asp_mask)[0]

    if len(candidates) == 0:
        candidates = np.where(area_ratio > 0.5)[0]
    if len(candidates) == 0:
        return None

    ink_mask = np.abs(ref_inks[candidates] - pua_ink) <= 0.25
    candidates = candidates[ink_mask]
    if len(candidates) == 0:
        return None

    return (
        ref_imgs[candidates],
        ref_inks[candidates],
        [ref_chars[int(i)] for i in candidates]
    )


def _match_pua(cp: int, pua_bf: np.ndarray, pua_img: np.ndarray,
               pua_ink: float) -> tuple:
    ref = _ref_data

    # 检查是否有已知修正
    if cp in KNOWN_FIXES:
        fixed_char = KNOWN_FIXES[cp]
        # 验证修正的分数
        try:
            idx = ref["chars"].index(fixed_char)
            score = _detailed_score(pua_img, pua_ink, ref["imgs"][idx], ref["inks"][idx])
            if score < 0.30:
                print(f"  [fix] U+{cp:04X} -> {fixed_char} (score={score:.4f})")
                return fixed_char, score
        except ValueError:
            # 参考集中不存在该字符（如超出范围），尝试动态加载
            try:
                tmp_font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", RENDER_SIZE, index=0)
                tmp_img, tmp_ink, _ = _render_char(tmp_font, fixed_char)
                score = _detailed_score(pua_img, pua_ink, tmp_img, tmp_ink)
                if score < 0.30:
                    print(f"  [fix] U+{cp:04X} -> {fixed_char} (dyn, score={score:.4f})")
                    return fixed_char, score
            except Exception:
                pass

    candidates = _filter_candidates(pua_bf, pua_ink,
                                    ref["imgs"], ref["inks"],
                                    ref["bboxes"], ref["chars"])
    if candidates is None:
        return None, 999.0

    best_char, best_score = _find_best_match(pua_img, pua_ink, pua_bf, candidates)

    # 如果最佳匹配是可疑罕见字，尝试高频字库
    if best_char and best_char in SUSPICIOUS_RARE:
        hf_indices = []
        for ch in set(HIGH_FREQ_CHARS):
            try:
                idx = ref["chars"].index(ch)
                hf_indices.append(idx)
            except ValueError:
                pass
        if hf_indices:
            hf = (
                ref["imgs"][hf_indices],
                ref["inks"][hf_indices],
                [ref["chars"][i] for i in hf_indices]
            )
            hf_char, hf_score = _find_best_match(pua_img, pua_ink, pua_bf, hf)
            if hf_char and hf_score < best_score - 0.01:
                print(f"  [fix] U+{cp:04X}: {best_char}->{hf_char} (s={best_score:.3f}->{hf_score:.3f})")
                best_char, best_score = hf_char, hf_score

    return best_char, best_score


# ==================== 主 API ====================

def download_font(font_url: str) -> bytes:
    resp = requests.get(font_url, timeout=30)
    resp.raise_for_status()
    return resp.content


def extract_font_url(html: str) -> Optional[str]:
    match = re.search(r'src:\s*url\(["\']?([^"\'()]+\.woff2)["\']?\)', html)
    if match:
        return match.group(1)
    match = re.search(r'src.*?url\(["\']?([^"\'()]+?\.woff2)["\']?\)', html)
    if match:
        return match.group(1)
    return None


def build_font_decoder(font_url: str) -> Dict[int, str]:
    if font_url in _font_cache:
        return _font_cache[font_url]

    print(f"[font_decoder] 下载字体: {font_url}")
    font_data = download_font(font_url)

    font_tt = TTFont(BytesIO(font_data))
    cmap = font_tt.getBestCmap()
    pua_cps = sorted([cp for cp in cmap if isinstance(cmap.get(cp), str)])
    print(f"[font_decoder] 发现 {len(pua_cps)} 个 PUA 编码点")

    ttf_path = "/tmp/_fanqie_font.ttf"
    font_tt.flavor = None
    font_tt.save(ttf_path)
    font_tt.close()

    pua_features = _extract_pua_features(ttf_path, pua_cps)
    _load_reference()

    pua_map: Dict[int, str] = {}

    # ========== 第一遍：硬编码字符集（零开销，100% 准确） ==========
    hc_hits = 0
    for cp in pua_cps:
        if cp in _FANQIE_HARDCODED_CHARSET:
            pua_map[cp] = _FANQIE_HARDCODED_CHARSET[cp]
            hc_hits += 1
    if hc_hits:
        print(f"[font_decoder] 硬编码字符集命中 {hc_hits}/{len(pua_cps)} 个")

    # ========== 第二遍：视觉匹配（仅对未覆盖的编码点） ==========
    unresolved = [cp for cp in pua_cps if cp not in pua_map]
    if unresolved:
        unique_matches: Dict[str, tuple] = {}
        for cp in unresolved:
            pua_bf = pua_features["bboxes"].get(cp)
            if pua_bf is None:
                continue
            pua_px = pua_features["pixels"].get(cp)
            if pua_px is None:
                continue
            best_char, best_score = _match_pua(cp, pua_bf, pua_px["img"], pua_px["ink"])

            if best_char and best_score < 0.35:
                if best_char in unique_matches:
                    existing_cp, existing_score = unique_matches[best_char]
                    if best_score < existing_score:
                        if existing_cp in pua_map:
                            del pua_map[existing_cp]
                        unique_matches[best_char] = (cp, best_score)
                        pua_map[cp] = best_char
                else:
                    unique_matches[best_char] = (cp, best_score)
                    pua_map[cp] = best_char

    print(f"[font_decoder] 解码结果: {len(pua_map)}/{len(pua_cps)} 个字符")
    if len(pua_map) < len(pua_cps):
        unmatched = [cp for cp in pua_cps if cp not in pua_map]
        print(f"[font_decoder] 未匹配: {len(unmatched)} 个")

    _font_cache[font_url] = pua_map
    return pua_map


def decode_content(content: str, pua_map: Dict[int, str]) -> str:
    result = []
    for c in content:
        cp = ord(c)
        if cp in pua_map:
            result.append(pua_map[cp])
        else:
            result.append(c)
    return ''.join(result)


# ==================== 便捷解码接口 ====================


def decode_pua_text(text: str, html: str = None) -> str:
    """
    便捷解码 PUA 加密文本。
    如果提供 html，自动从中提取字体 URL 并构建解码器。
    """
    if not text:
        return text
    font_url = None
    if html:
        font_url = extract_font_url(html)
    if not font_url:
        return text
    try:
        pua_map = build_font_decoder(font_url)
        return decode_content(text, pua_map)
    except Exception as e:
        print(f"[font_decoder] PUA 解码失败: {e}")
        return text


# ==================== 测试入口 ====================

def quick_test():
    test_url = "https://lf6-awef.bytetos.com/obj/awesome-font/c/dc027189e0ba4cd.woff2"
    mapping = build_font_decoder(test_url)

    print("\n--- 映射表样本 ---")
    for i, (cp, ch) in enumerate(sorted(mapping.items())[:25]):
        print(f"  U+{cp:04X} -> {ch}")

    import os
    from database import get_connection
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT content_path FROM chapters WHERE source='fanqie' LIMIT 1")
    row = cur.fetchone()
    conn.close()

    if row and row.get('content_path'):
        base = os.path.dirname(__file__)
        content_path = os.path.join(base, row['content_path'])
        if os.path.exists(content_path):
            with open(content_path, 'r', encoding='utf-8') as f:
                encrypted = f.read()
            decoded = decode_content(encrypted, mapping)
            pua_count = sum(1 for c in encrypted if 0xE000 <= ord(c) <= 0xF8FF)
            print(f"\n--- 解码前后对比 ---")
            print(f"原文前150字: {encrypted[:150]}")
            print(f"解码后前150字: {decoded[:150]}")
            print(f"\n统计: 原文 {len(encrypted)} 字, PUA {pua_count} 个")
        else:
            print(f"⛔ 内容文件不存在: {content_path}")


if __name__ == '__main__':
    quick_test()
