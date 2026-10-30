#!/usr/bin/env python3
"""对抗战竞技场 (Taikousen Arena) 简体中文补丁。

用法:
    python patch.py [游戏目录]          打补丁（默认目录为当前目录）
    python patch.py [游戏目录] --restore 还原为原版文件

补丁会修改以下三个文件，首次运行时自动备份为 *.orig：
    Taikousen Arena_Data/data.unity3d                         文本、字体、界面文字
    GameAssembly.dll                                          改为读取内置翻译表（不再从官方服务器下载日文表）
    Taikousen Arena_Data/il2cpp_data/Metadata/global-metadata.dat   代码中的少量提示文字
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import sys

FROZEN = getattr(sys, "frozen", False)
ROOT = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from sentence_csv import build_csv, parse_records  # noqa: E402

GAME_VERSION = "4.1.2"
DATA_DIR = "Taikousen Arena_Data"
BUNDLE = os.path.join(DATA_DIR, "data.unity3d")
ASSEMBLY = "GameAssembly.dll"
METADATA = os.path.join(DATA_DIR, "il2cpp_data", "Metadata", "global-metadata.dat")

ORIGINAL_SHA256 = {
    BUNDLE: "0aff20df34d2917eb6f0689978b3b14cb5b9bbc7b5f1b83185967dcb44b79b25",
    ASSEMBLY: "5745fbead96e288b687f0b5d7d95ed8b7cbbb46ebc2339aa97e40357adbe3544",
    METADATA: "11c02931c268fb7c520febf60c517292698df3454f84ad78e5c78fc307bcc8ab",
}

# Sentence.Init(): `if (Const.VersionType == 2) LoadCsvFromUrlsSync(); else Resources.LoadAll("Sentence")`.
# Release builds set VersionType = 2, so the game downloads the Japanese tables on every start.
# NOP-ing the `je` makes it read the (translated) tables bundled in resources.assets instead.
SENTENCE_INIT_JE_OFFSET = 0x4B9391
SENTENCE_INIT_PATTERN = re.compile(
    rb"\x83\x38\x02(\x74.)\x48\x8B\x15....\x48\x8B\x0D....\xE8....\x48\x8B\xD8\x33\xFF\x8B\xC7\x48\x85\xDB",
    re.DOTALL,
)

CSV_ASSETS = {
    "BADCG_Translate - System": "system.zh.json",
    "BADCG_Translate - Card": "card.zh.json",
}

# (Font object, replacement font file, family, style) and the TMP font assets that render with it.
FONTS = {
    "NotoSansJP-Medium": ("NotoSansCJKsc-Medium-subset.otf", "Noto Sans CJK SC", "Medium"),
    "851Gkktt_005": ("NotoSansCJKsc-Bold-subset.otf", "Noto Sans CJK SC", "Bold"),
}
FONT_ASSETS = {
    "NotoSansJP-Medium SDF": ("NotoSansJP-Medium", "Medium"),
    "851Gkktt_005 SDF": ("851Gkktt_005", "Bold"),
}

TMP_TEXT_OFFSET = 88  # m_text of a TextMeshProUGUI with an empty m_Name and no cull-state listeners


def res(*parts):
    return os.path.join(ROOT, *parts)


def load_json(*parts):
    with open(res(*parts), encoding="utf-8") as f:
        return json.load(f)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------- GameAssembly.dll

def patch_assembly(data):
    data = bytearray(data)
    off = SENTENCE_INIT_JE_OFFSET
    if data[off - 3:off + 2] != b"\x83\x38\x02\x74\x50":
        matches = list(SENTENCE_INIT_PATTERN.finditer(data))
        if len(matches) != 1:
            raise RuntimeError("GameAssembly.dll 中找不到要修改的位置（游戏版本可能不是 %s）" % GAME_VERSION)
        off = matches[0].start(1)
    data[off:off + 2] = b"\x90\x90"
    return bytes(data)


# ---------------------------------------------------------------- global-metadata.dat

def patch_metadata(data, mapping):
    """Point string literals at UTF-8 data appended to the end of the file."""
    data = bytearray(data)
    magic, _version = struct.unpack_from("<Ii", data, 0)
    if magic != 0xFAB11BAF:
        raise RuntimeError("global-metadata.dat 格式不正确")
    lit_off, lit_size, data_off, _data_size = struct.unpack_from("<iiii", data, 8)
    wanted = {k.encode("utf-8"): v.encode("utf-8") for k, v in mapping.items()}
    done = set()
    for i in range(lit_size // 8):
        length, index = struct.unpack_from("<Ii", data, lit_off + 8 * i)
        old = bytes(data[data_off + index:data_off + index + length])
        new = wanted.get(old)
        if new is None:
            continue
        pos = len(data)
        data += new
        struct.pack_into("<Ii", data, lit_off + 8 * i, len(new), pos - data_off)
        done.add(old)
    return bytes(data), [k.decode("utf-8") for k in wanted if k not in done]


# ---------------------------------------------------------------- data.unity3d

def translate_csv(text, zh):
    bom = text.startswith("﻿")
    records = parse_records(text)
    out = [records[0]]
    for key, jp, kr in records[1:]:
        new = zh.get(key, jp)
        if "\r\n" in jp:
            new = new.replace("\r\n", "\n").replace("\n", "\r\n")
        # An empty KR cell falls back to JP in game; keep Korean players on the original text.
        out.append((key, new, kr if kr.strip() else jp))
    return build_csv(out, bom=bom), sum(1 for r in records[1:] if r[0] in zh)


def read_tmp_text(raw):
    if len(raw) < TMP_TEXT_OFFSET + 4:
        return None
    length = struct.unpack_from("<i", raw, TMP_TEXT_OFFSET)[0]
    start = TMP_TEXT_OFFSET + 4
    if length <= 0 or start + length > len(raw):
        return None
    try:
        return raw[start:start + length].decode("utf-8"), start + length
    except UnicodeDecodeError:
        return None


def replace_tmp_text(raw, end, new):
    def align(n):
        return (n + 3) & ~3

    body = new.encode("utf-8")
    head = raw[:TMP_TEXT_OFFSET] + struct.pack("<i", len(body)) + body
    head += b"\x00" * (align(len(head)) - len(head))
    return head + raw[align(end):]


class Bundle:
    def __init__(self, path):
        import UnityPy

        self.env = UnityPy.load(path)
        self.bundle = next(iter(self.env.files.values()))
        self.files = {name: f for name, f in self.bundle.files.items() if hasattr(f, "objects")}
        self._scripts = {}

    def resolve(self, assets_file, file_id, path_id):
        target = assets_file
        if file_id:
            name = assets_file.externals[file_id - 1].path.replace("\\", "/").split("/")[-1]
            target = self.files.get(name)
        return target.objects.get(path_id) if target is not None else None

    def script_class(self, obj):
        raw = obj.get_raw_data()
        file_id, path_id = struct.unpack_from("<iq", raw, 16)
        key = (obj.assets_file.name, file_id, path_id)
        if key not in self._scripts:
            script = self.resolve(obj.assets_file, file_id, path_id)
            self._scripts[key] = script.read().m_ClassName if script is not None else None
        return self._scripts[key]


def patch_bundle(src, dst, verbose=True):
    from UnityPy.helpers.TypeTreeNode import TypeTreeNode

    csv_tr = {name: load_json("translation", fn) for name, fn in CSV_ASSETS.items()}
    ui_tr = load_json("translation", "ui_strings.zh.json")
    font_node = TypeTreeNode.from_list(load_json("tools", "typetrees", "TMP_FontAsset.json"))

    log("读取 data.unity3d ...")
    b = Bundle(src)
    seen_csv, seen_fonts, seen_assets, ui_hits = set(), set(), set(), {}

    for obj in b.env.objects:
        kind = obj.type.name
        if kind == "TextAsset":
            data = obj.read()
            if data.m_Name in csv_tr:
                text, n = translate_csv(data.m_Script, csv_tr[data.m_Name])
                data.m_Script = text
                data.save()
                seen_csv.add(data.m_Name)
                log("  翻译表 %s：%d 条" % (data.m_Name, n))
        elif kind == "Font":
            tree = obj.read_typetree()
            if tree["m_Name"] in FONTS and obj.assets_file.name == "sharedassets0.assets":
                font_file, family, _style = FONTS[tree["m_Name"]]
                with open(res("fonts", font_file), "rb") as f:
                    tree["m_FontData"] = list(f.read())
                tree["m_FontNames"] = [family]
                obj.save_typetree(tree)
                seen_fonts.add(tree["m_Name"])
                log("  字体 %s → %s" % (tree["m_Name"], font_file))
        elif kind == "MonoBehaviour":
            cls = b.script_class(obj)
            if cls == "TMP_FontAsset":
                tree = obj.read_typetree(font_node)
                if tree["m_Name"] not in FONT_ASSETS or obj.assets_file.name != "sharedassets0.assets":
                    continue
                source_font, style = FONT_ASSETS[tree["m_Name"]]
                patch_font_asset(b, obj, tree, source_font, style)
                obj.save_typetree(tree, font_node)
                seen_assets.add(tree["m_Name"])
                log("  TMP 字体资源 %s 已清空字形缓存（运行时按需生成中文字形）" % tree["m_Name"])
            elif cls == "TextMeshProUGUI":
                raw = obj.get_raw_data()
                found = read_tmp_text(raw)
                if found and found[0] in ui_tr:
                    obj.set_raw_data(replace_tmp_text(raw, found[1], ui_tr[found[0]]))
                    ui_hits[found[0]] = ui_hits.get(found[0], 0) + 1

    missing = (set(CSV_ASSETS) - seen_csv) | (set(FONTS) - seen_fonts) | (set(FONT_ASSETS) - seen_assets)
    if missing:
        raise RuntimeError("data.unity3d 中缺少以下资源：%s" % ", ".join(sorted(missing)))
    log("  界面文字：替换 %d 处（%d/%d 种）" % (sum(ui_hits.values()), len(ui_hits), len(ui_tr)))
    if verbose:
        for k in ui_tr:
            if k not in ui_hits:
                log("    未找到：%r" % k)

    log("写入 data.unity3d（压缩需要一两分钟）...")
    out = b.bundle.save(packer="original")
    tmp = dst + ".tmp"
    with open(tmp, "wb") as f:
        f.write(out)
    os.replace(tmp, dst)


def patch_font_asset(b, obj, tree, source_font, style):
    """Point the asset at the Chinese font and drop every glyph baked from the old font.

    Glyph indices differ between fonts, so stale glyph/character/kerning tables would map new
    characters onto old atlas cells. With empty tables the dynamic asset rebuilds them at runtime.
    """
    if tree["m_AtlasPopulationMode"] != 1:
        raise RuntimeError("%s 不是动态字体资源" % tree["m_Name"])
    font = next(o for o in obj.assets_file.objects.values()
                if o.type.name == "Font" and o.read_typetree()["m_Name"] == source_font)
    tree["m_SourceFontFile"] = {"m_FileID": 0, "m_PathID": font.path_id}
    tree["m_GlyphTable"] = []
    tree["m_CharacterTable"] = []
    tree["m_UsedGlyphRects"] = []
    pack = 0 if tree["m_AtlasRenderMode"] & 0x10 else 1
    tree["m_FreeGlyphRects"] = [{"m_X": 0, "m_Y": 0, "m_Width": tree["m_AtlasWidth"] - pack,
                                 "m_Height": tree["m_AtlasHeight"] - pack}]
    tree["m_AtlasTextureIndex"] = 0
    for key, value in tree["m_FontFeatureTable"].items():
        if isinstance(value, list):
            tree["m_FontFeatureTable"][key] = []
    for key, value in tree["m_KerningTable"].items():
        if isinstance(value, list):
            tree["m_KerningTable"][key] = []
    tree["m_FaceInfo"]["m_FamilyName"] = "Noto Sans CJK SC"
    tree["m_FaceInfo"]["m_StyleName"] = style


# ---------------------------------------------------------------- driver

def find_game_dir(arg):
    candidates = [arg] if arg else [os.getcwd(), os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))]
    for c in candidates:
        if c and os.path.isfile(os.path.join(c, BUNDLE)) and os.path.isfile(os.path.join(c, ASSEMBLY)):
            return os.path.abspath(c)
    raise RuntimeError("找不到游戏目录。请把本程序放到「Taikousen Arena.exe」所在的文件夹中运行，"
                       "或在命令行中指定游戏目录。")


def originals(game):
    """Back up each target once and return {relpath: (original, target)}."""
    out = {}
    for rel in (BUNDLE, ASSEMBLY, METADATA):
        target = os.path.join(game, rel)
        orig = target + ".orig"
        if not os.path.exists(orig):
            log("备份 %s → %s" % (rel, os.path.basename(orig)))
            shutil.copy2(target, orig)
        out[rel] = (orig, target)
    return out


def restore(game):
    for rel in (BUNDLE, ASSEMBLY, METADATA):
        target = os.path.join(game, rel)
        if os.path.exists(target + ".orig"):
            shutil.copy2(target + ".orig", target)
            log("已还原 %s" % rel)
        else:
            log("没有备份，跳过 %s" % rel)


def main():
    ap = argparse.ArgumentParser(description="对抗战竞技场 简体中文补丁")
    ap.add_argument("game_dir", nargs="?", help="游戏目录（含 Taikousen Arena.exe）")
    ap.add_argument("--restore", action="store_true", help="还原为原版文件")
    ap.add_argument("--force", action="store_true", help="游戏版本不符时仍尝试打补丁")
    args = ap.parse_args()

    game = find_game_dir(args.game_dir)
    log("游戏目录：%s" % game)
    if args.restore:
        restore(game)
        return

    files = originals(game)
    mismatched = [rel for rel, (orig, _) in files.items() if sha256(orig) != ORIGINAL_SHA256[rel]]
    if mismatched:
        log("警告：以下文件与 %s 版不一致：%s" % (GAME_VERSION, ", ".join(mismatched)))
        if not args.force:
            raise RuntimeError("本补丁适用于 %s 版。如需强行尝试，请加上 --force 参数。" % GAME_VERSION)

    orig, target = files[ASSEMBLY]
    with open(orig, "rb") as f:
        data = patch_assembly(f.read())
    with open(target, "wb") as f:
        f.write(data)
    log("GameAssembly.dll：已改为读取内置翻译表")

    orig, target = files[METADATA]
    with open(orig, "rb") as f:
        data, missed = patch_metadata(f.read(), load_json("translation", "code_strings.zh.json"))
    with open(target, "wb") as f:
        f.write(data)
    log("global-metadata.dat：代码文字已替换%s" % ("（未找到 %d 条）" % len(missed) if missed else ""))

    orig, target = files[BUNDLE]
    patch_bundle(orig, target)
    log("完成！启动游戏后，在设置中选择「日本語」（现显示为简体中文）即可。")


if __name__ == "__main__":
    code = 0
    try:
        main()
    except Exception as e:  # noqa: BLE001 - show a readable message to players
        log("出错：%s" % e)
        code = 1
    if FROZEN:
        input("按回车键退出...")
    sys.exit(code)
