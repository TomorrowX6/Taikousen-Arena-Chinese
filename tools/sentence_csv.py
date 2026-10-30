"""Replica of the game's CSV handling (Sentence.FileToADDDic), recovered from the IL2CPP build.

The game reads the file character by character: '"' toggles the quoted state and is kept,
'\\r' is dropped outside quotes, ',' and '\\n' end a field outside quotes. Every field is then
un-escaped (`""` -> `"`, one leading and one trailing quote stripped). The flat field list is
consumed three at a time as (ID, JP, KR); an empty/whitespace KR falls back to JP.
"""


def _to_str(raw):
    s = raw.replace('""', '"')
    start = 1 if s.startswith('"') else 0
    end = len(s) - (1 if s.endswith('"') else 0)
    return s[start:end] if end >= start else ""


def parse_fields(text):
    fields, buf, quoted = [], [], False
    for ch in text:
        if ch == '"':
            quoted = not quoted
            buf.append(ch)
        elif ch == "\r":
            if quoted:
                buf.append(ch)
        elif ch in ",\n" and not quoted:
            fields.append(_to_str("".join(buf)))
            buf = []
        else:
            buf.append(ch)
    if buf:
        fields.append(_to_str("".join(buf)))
    return fields


def parse_records(text):
    """Return [(id, jp, kr), ...] in file order, exactly as the game pairs the fields."""
    if text.startswith("﻿"):
        text = text[1:]
    f = parse_fields(text)
    return [(f[i], f[i + 1], f[i + 2]) for i in range(0, len(f) - 2, 3)]


def _quote(s):
    if any(c in s for c in ',"\r\n'):
        return '"' + s.replace('"', '""') + '"'
    return s


def build_csv(records, bom=True):
    body = "\r\n".join(",".join(_quote(x) for x in r) for r in records) + "\r\n"
    return ("﻿" if bom else "") + body
