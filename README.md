# 对抗战竞技场（対抗戦アリーナ / Taikousen Arena）简体中文补丁

适用版本：**4.1.2（Windows 版，BOOTH 发布）**

本补丁把游戏里的日文文字翻译成简体中文，并换上可以显示简体中文的字体。

## 汉化范围

| 内容 | 状态 |
| --- | --- |
| 全部卡牌名称、卡牌效果、关键词能力（537 条） | ✅ |
| 对战提示、菜单提示、任务、称号、商店等系统文本（370 条） | ✅ |
| 界面里的文字标签（设置项、确认框等 30 处） | ✅ |
| 代码中的任务模板、部分错误提示（14 条） | ✅ |
| 字体：Noto Sans CJK SC（思源黑体）Medium / Bold | ✅ |
| 做成图片的按钮和标题（如「デッキ」「バトル」等） | ❌ 仍为日文 |

韩语模式不受影响，仍显示原版韩文。

## 使用方法

### 方法一：Windows 补丁程序（推荐）

1. 在本仓库的 **Actions → Build patcher** 页面打开最新一次成功的运行，下载 `TaikousenArena-zh-patch` 压缩包并解压。
2. 把 `TaikousenArena-zh-patch.exe` 放进游戏文件夹（和 `Taikousen Arena.exe` 放在一起）。
3. 双击运行，等待一两分钟，看到「完成！」即可。
4. 启动游戏。

> PyInstaller 打包的程序有时会被杀毒软件误报，可以改用方法二。

### 方法二：Python 脚本

需要 Python 3.9 及以上版本。

```bash
pip install -r requirements.txt
python patch.py "D:\Games\Taikousen Arena"
```

### 还原

补丁第一次运行时会把被修改的三个文件备份为 `*.orig`。还原方法：

```bash
python patch.py "游戏目录" --restore
```

或者手动把 `.orig` 文件改回原来的名字。

## 补丁修改了什么

| 文件 | 修改内容 |
| --- | --- |
| `Taikousen Arena_Data/data.unity3d` | 替换翻译表 `BADCG_Translate - System/Card` 的日文栏；把 `NotoSansJP-Medium` 和 `851Gkktt_005` 两个字体换成思源黑体 SC；清空对应 TMP 字体资源的字形缓存（游戏运行时会按需生成中文字形）；替换 30 处界面文字 |
| `GameAssembly.dll` | 修改 2 个字节。原版每次启动都会从官方服务器下载日文翻译表；修改后改为读取游戏内置的（已汉化）翻译表 |
| `global-metadata.dat` | 替换 14 条写在代码里的文字（任务模板、提示信息） |

游戏规则、联机逻辑都没有改动，所以可以照常和日服、韩服玩家对战，对方看到的仍是他们自己的语言。

## 仓库结构

```
patch.py                         补丁程序
translation/system.zh.json       系统文本（键为游戏内 ID）
translation/card.zh.json         卡牌文本
translation/ui_strings.zh.json   界面文字（日文原文 → 中文）
translation/code_strings.zh.json 代码中的文字（日文原文 → 中文）
fonts/                           思源黑体 SC 子集（SIL OFL 1.1）
tools/sentence_csv.py            按游戏的方式解析 / 生成翻译表 CSV
tools/typetrees/                 TMP_FontAsset 的序列化结构
```

改进翻译只需要编辑 `translation/` 下的 JSON 文件，然后重新运行补丁即可（补丁总是基于 `.orig` 原版文件重新生成）。

## 译名

角色名、学校名、社团名参考《蔚蓝档案》国服译名，例如：阿罗娜、普拉娜、夏莱、阿拜多斯、格黑娜、圣三一、千年、便利屋68、补习部、游戏开发部。

常用卡牌术语：出击（出撃）、神秘解放（神秘開放）、保健室、矫正局、手牌、牌库、压制（制圧）、疲劳 / 活跃（疲労 / 元気）、嘲讽（挑発）、永续（永続）、费用（コスト）。

## 注意事项

- 本补丁是非官方的粉丝汉化，与对抗战竞技场开发组及《蔚蓝档案》官方无关。
- 原版说明书写明「禁止对本软件进行改造及解析」「禁止转载及分发本软件」。使用补丁前请自行确认并承担风险。本仓库不包含任何游戏文件，请勿分发打过补丁的游戏本体。
- 游戏更新后补丁可能失效，补丁检测到版本不符时会停止运行。

## 授权

- 翻译文本与补丁代码：仅供个人学习交流使用。
- 字体：Noto Sans CJK SC，© Adobe，SIL Open Font License 1.1，见 `fonts/OFL.txt`。
