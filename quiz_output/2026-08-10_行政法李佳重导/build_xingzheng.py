# -*- coding: utf-8 -*-
"""李佳行政法 5 份 MinerU OCR -> 结构化题库（锚定[解析]版，最稳）。
策略：以每个 [解析] 为锚点（每题必有一个，共434），向后回溯定位题干行；
无 [解析] 的伪题(法条/噪声)直接丢弃。答案取解析「本题答案为 X」(含LaTeX)。
"""
import json, re, os
from collections import Counter

SRC = [
 r"D:\新建文件夹 (2)\2026客观真金题行政李佳(OCR)_1-60.pdf-3caf6e19-4a73-4632-8854-0a605ae003d2\MinerU_markdown_202608100018478_43a88574.md",
 r"D:\新建文件夹 (2)\2026客观真金题行政李佳(OCR)_61-120.pdf-dcd2980a-6fbe-4cfd-8846-f0332f4e750b\MinerU_markdown_202608100019464_229268e4.md",
 r"D:\新建文件夹 (2)\2026客观真金题行政李佳(OCR)_121-180.pdf-c8fd0af6-7283-4d83-b880-2a77edc9bd27\MinerU_markdown_202608100019622_0cfe0df8.md",
 r"D:\新建文件夹 (2)\2026客观真金题行政李佳(OCR)_181-240.pdf-fbbd8fb5-4921-49d9-a314-012065c1b12a\MinerU_markdown_202608100020351_c10cdcb3.md",
 r"D:\新建文件夹 (2)\2026客观真金题行政李佳(OCR)_241-293.pdf-b4bc5d3c-f45d-43fc-9771-7b17592638ff\MinerU_markdown_202608100020980_6a21a20d.md",
]
OUT = r"D:\测试\quiz_output\2026-08-10_行政法李佳重导"

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳⓪"
Q_RE = re.compile(r'^\s*(\d+)\s*[.、．]\s')
HEADER_RE = re.compile(r'^\[(解析|设题陷阱与常见错误分析|归纳总结|技术流|考点)\]')
OPTION_LINE_RE = re.compile(r'^\s*[A-E][.、．]')
PROJECT_RE = re.compile(r'^#\s*PROJECT')
TOPIC_RE = re.compile(r'^#\s*专题[一二三四五六七八九十\d]*\s*(.*)')
SUBSEC_RE = re.compile(r'^##\s+([一二三四五六七八九十]+[、.]|第[一二三四五六七八九十\d]+[、.]|[0-9]+[、.])')
TYPE_RE = re.compile(r'[，,]\s*(单|多|不定项)\s*[)）]')
YEAR_RE = re.compile(r'(?:19|20)\d{2}')
FOOTNOTE_RE = re.compile(r'^\s*[' + CIRCLED + r']')
OPT_RE = re.compile(r'([A-E])\.\s*(.*?)(?=\s*[A-E]\.|\s*$)', re.S)
OPT_FRAG_RE = re.compile(r'\s*[A-E]\..*?(?=\s*[A-E]\.|\s*$)', re.S)

def clean_circled(t):
    for ch in CIRCLED:
        t = t.replace(ch, '')
    return t
def strip_hash(t):
    return re.sub(r'^#+\s*', '', t)
def next_line_is_opt(lines, j):
    k = j + 1
    while k < len(lines) and not lines[k].strip():
        k += 1
    return k < len(lines) and OPTION_LINE_RE.match(lines[k].strip())
def is_stem_line(line):
    if not Q_RE.match(line):
        return False
    s = line.strip()
    if '？' in s or '?' in s: return True
    if TYPE_RE.search(s): return True
    if re.search(r'(?<=\s)[A-E]\.', s): return True  # 内联选项
    return False
def clean_head(lines):
    out = []
    for l in lines:
        s = l.strip()
        if not s or s == '续表' or s == '续表：' or re.match(r'^\d+$', s):
            continue
        out.append(re.sub(r'续表', '', l))
    return out
def extract_options(head):
    flat = ' '.join(l.strip() for l in clean_head(head))
    return {m.group(1): re.sub(r'\s+', ' ', m.group(2)).strip() for m in OPT_RE.finditer(flat)}
def remove_option_fragments(head):
    return re.sub(r'\n', ' ', head) and OPT_FRAG_RE.sub('', re.sub(r'\n', ' ', head)).strip()
def extract_answer(text):
    m = re.search(r'本题答案为[:：]?\s*([A-E][A-E、，,\s]*?)(?=[。.\s]|$)', text)
    if m: return re.sub(r'[^A-E]', '', m.group(1)).upper()
    m = re.search(r'本题答案为[:：]?\s*\$?\\?(?:mathrm|text)\{([A-E]+)\}', text)
    if m: return m.group(1).upper()
    m = re.search(r'答案为[:：]?\s*([A-E][A-E、，,\s]*?)(?=[。.\s]|$)', text)
    if m: return re.sub(r'[^A-E]', '', m.group(1)).upper()
    m = re.search(r'[为选]\s*([A-E])\s*选项', text)
    if m: return m.group(1).upper()
    return ''

def main():
    all_lines = []
    for path in SRC:
        all_lines += open(path, encoding='utf-8').read().split('\n')
    n = len(all_lines)
    # 预扫章节状态
    bz, zj = '', ''
    hdr = [('', '')] * n
    for i, raw in enumerate(all_lines):
        s = raw.strip()
        if s.startswith('#'):
            if TOPIC_RE.match(s):
                bz = TOPIC_RE.match(s).group(1).strip(); zj = ''
            elif SUBSEC_RE.match(s):
                h = SUBSEC_RE.match(s).group(1).strip()
                if '命题规律' not in h: zj = h
            elif PROJECT_RE.match(s):
                zj = ''
        hdr[i] = (bz, zj)
    # 找所有 [解析] 锚点
    anchors = [i for i in range(n) if (lambda m: m and m.group(1)=='解析')(HEADER_RE.match(all_lines[i].strip()))]
    questions = []
    for k, ai in enumerate(anchors):
        bz, zj = hdr[ai]
        # 题干回溯：在 [上锚点结束, ai) 内找最后一个题干行
        lo = (anchors[k-1] + 1) if k > 0 else 0
        stem_start = None
        for j in range(ai - 1, lo - 1, -1):
            if is_stem_line(all_lines[j]) or (Q_RE.match(all_lines[j]) and next_line_is_opt(all_lines, j)):
                stem_start = j; break
        if stem_start is None:
            stem_start = lo
        head_region = all_lines[stem_start:ai]
        # 解析区：[ai, 下一锚点/下一题干/下一结构标题)
        j = ai + 1
        while j < n:
            s = all_lines[j].strip()
            if (lambda m: m and m.group(1)=='解析')(HEADER_RE.match(s)): break
            if is_stem_line(all_lines[j]) or (Q_RE.match(all_lines[j]) and next_line_is_opt(all_lines, j)): break
            if s.startswith('#') and (PROJECT_RE.match(s) or TOPIC_RE.match(s) or SUBSEC_RE.match(s)): break
            j += 1
        ana_region = all_lines[ai:j]
        # 解析分段
        segs = []
        cur_label = None; cur_txt = []
        def flush():
            nonlocal cur_label, cur_txt
            if cur_label is not None:
                segs.append([cur_label, '\n'.join(cur_txt)])
            cur_label = None; cur_txt = []
        for line in ana_region:
            s = line.strip()
            if not s or s in ('续表', '续表：') or re.match(r'^\d+$', s):  # 噪声
                continue
            if FOOTNOTE_RE.match(s):  # 脚注独立行
                continue
            hm = HEADER_RE.match(s)
            if hm:
                flush(); cur_label = hm.group(1); cur_txt = [HEADER_RE.sub('', line).strip()]
            else:
                t = strip_hash(line)
                if cur_label is None:
                    cur_label = '解析'; cur_txt = [t]
                else:
                    cur_txt.append(t)
        flush()
        # 题干
        ch = clean_head(head_region)
        stem0 = Q_RE.sub('', ch[0], count=1).strip() if ch else ""
        extra = remove_option_fragments('\n'.join(ch[1:])) if len(ch) > 1 else ""
        stem = clean_circled((stem0 + ' ' + extra).strip())
        opts = extract_options(head_region)
        opt_fields = {f'选项{k}': opts.get(k, '') for k in 'ABCDE'}
        # 解析文本
        parsed = ""
        for label, txt in segs:
            t = clean_circled(txt).strip()
            if not t: continue
            parsed += label + '：\n' + t + '\n\n'
        parsed = parsed.strip('\n')
        # 答案
        ans = ''
        for label, txt in segs:
            if label == '解析':
                a = extract_answer(txt)
                if a: ans = a; break
        if not ans:
            ans = extract_answer('\n'.join(t for _, t in segs))
        # 题型/年份
        typ = ''
        tm = TYPE_RE.search(stem0)
        if tm: typ = {'单':'单选','多':'多选','不定项':'不定项'}.get(tm.group(1), '')
        if not typ: typ = '多选' if len(ans) > 1 else ('单选' if len(ans) == 1 else '')
        ym = YEAR_RE.search(stem0); year = ym.group(0) if ym else ''
        missing = [k for k in 'ABCD' if not opt_fields[f'选项{k}']]
        status, note = '已发布', ''
        if not ans:
            status = '草稿'; note = '答案未定位(待核)'
        if missing:
            status = '草稿'
            note = (note + ';' if note else '') + '缺选项' + ''.join(missing)
        questions.append({
            '题目ID': 'xingzheng-%03d' % (len(questions) + 1), '科目': '行政法', '编章': bz, '章节': zj,
            '题型': typ, '题干': stem,
            '选项A': opt_fields['选项A'], '选项B': opt_fields['选项B'], '选项C': opt_fields['选项C'],
            '选项D': opt_fields['选项D'], '选项E': opt_fields['选项E'],
            '答案': ans, '解析': parsed, '考点': '', '难度': '', '来源': '李佳行政法真金题',
            '年份': year, '状态': status, '排序': len(questions) + 1, '备注': note,
        })
    # 丢弃无解析伪题（理论上已无，保险）
    before = len(questions)
    questions = [q for q in questions if q['解析'].strip()]
    # 写文件
    os.makedirs(OUT, exist_ok=True)
    for name, obj in [('parsed.json', questions), ('feishu_records.json', questions),
                      ('questions.行政法.import.json', {'subject':'行政法','total':len(questions),'updated':'2026-08-10','questions':questions})]:
        json.dump(obj, open(os.path.join(OUT, name), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    import csv
    cols = ['题目ID','科目','编章','章节','题型','题干','选项A','选项B','选项C','选项D','选项E','答案','解析','考点','难度','来源','年份','状态','排序','备注']
    with open(os.path.join(OUT, '题库.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for r in questions: w.writerow(r)
    rep = ['# 行政法李佳重导 核对报告', '', f'- 解析题数：**{len(questions)}** (预期434，丢弃伪题{before-len(questions)})',
           f'- 草稿(无答案)：{sum(1 for r in questions if r["状态"]=="草稿")}',
           f'- 缺选项题数：{sum(1 for r in questions if any(r[f"选项{k}"]=="" for k in "ABCD"))}', '',
           '## 题型分布'] + [f'- {k}: {v}' for k, v in Counter(r['题型'] for r in questions).items()]
    flags = [(r['题目ID'], r['备注'], r['题干'][:20]) for r in questions if r['备注']]
    if flags:
        rep += ['', '## 待核清单'] + [f'- {q} [{w}] {s}' for q, w, s in flags]
    open(os.path.join(OUT, '核对报告.md'), 'w', encoding='utf-8').write('\n'.join(rep))
    print('解析题数:', len(questions), '(丢弃', before-len(questions), '伪题)')
    print('草稿:', sum(1 for r in questions if r['状态']=='草稿'), '| 缺选项:', sum(1 for r in questions if any(r[f'选项{k}']=='' for k in 'ABCD')))
    print('题型:', dict(Counter(r['题型'] for r in questions)))

if __name__ == '__main__':
    main()
