# -*- coding: utf-8 -*-
"""
解析 5 份「2026法大金题解析--商法、经济法、知产法」MinerU OCR markdown，
按用户规则生成飞书导入包。

规则：
- 答案取解析中「本题选」后的字母（【答案】后①②③④不作为答案 —— 本批源无【答案】字段，答案只在解析）。
- 考点、思路、解析 全部合并进「解析」字段，段落之间空 0.5 行（保留原空行）。
- 题目和解析都两端对齐（前端 CSS 控制，数据层不处理）。
- 删除 ①②③④ 及脚注；删除脚注内容（## [1] AC [2] A 这种脚注块）、页码数字、[n]/$^{[n]}$ 内联脚注标记。
- 选项 A-E 每个选项另起一行（源中常内联，需拆出）。
- 保留 <table>（本批无，但做兼容）。
"""
import os, re, json, glob

SRC = [
    r"D:/新建文件夹 (2)/2026法大金题解析--商法、经济法、知产法_Password_Removed(OCR)(1)_1-71.pdf-e6e2d32e-d652-48ed-9d43-cf7046580a9d/MinerU_markdown_202608100101259_bd73f1ba.md",
    r"D:/新建文件夹 (2)/2026法大金题解析--商法、经济法、知产法_Password_Removed(OCR)(1)_72-142.pdf-9caf59ce-9f65-4e28-b6d3-a189b4e36ca9/MinerU_markdown_202608100101738_9bd4107d.md",
    r"D:/新建文件夹 (2)/2026法大金题解析--商法、经济法、知产法_Password_Removed(OCR)(1)_143-213.pdf-fdc60dd7-0b2c-405d-ad33-304c51853504/MinerU_markdown_202608100101322_a80004b2.md",
    r"D:/新建文件夹 (2)/2026法大金题解析--商法、经济法、知产法_Password_Removed(OCR)(1)_214-284.pdf-21845263-a236-421c-ae36-0670b5ab872b/MinerU_markdown_202608100101966_362ae613.md",
    r"D:/新建文件夹 (2)/2026法大金题解析--商法、经济法、知产法_Password_Removed(OCR)(1)_285-352.pdf-18feff3d-d4e7-49d7-a143-3312e138f718/MinerU_markdown_202608100100059_ff359f74.md",
]
OUT = os.path.dirname(os.path.abspath(__file__))

# ---------- 正则 ----------
Q_RE       = re.compile(r'^\s*(\d+)\.\s')                 # 题号行
HDR_RE     = re.compile(r'^#{1,6}\s*(.*)$')               # 任意层级标题（按 第X章/第X节 归类）
KD_RE      = re.compile(r'【考点】\s*(.*)')                # 考点标签行
OPT_MARK   = re.compile(r'(?<![A-Za-z])([A-E])\.(?=[\s\u4e00-\u9fff])')  # 选项标记（允许 A.甲 或 A. 甲）
FOOTNOTE_BLOCK = re.compile(r'^#{1,6}\s*\[\d+\].*$')       # ## [1] AC [2] A 脚注块
PAGE_NUM   = re.compile(r'^\s*\d{1,4}\s*$')                # 独立页码行
INLINE_FN  = re.compile(r'\[\d+\]')                        # [1] 内联脚注
LATEX_FN1  = re.compile(r'\$\s*\^\{\[[0-9]+\]\}\s*\$')     # $^{[2]}$
LATEX_FN2  = re.compile(r'\^\{\[[0-9]+\]\}')               # ^{[2]}
ANSWER_RE  = re.compile(r'本题选\s*[:：]?\s*([A-Ea-e]+)')   # 本题选 D / 本题选 ACD
TYPE_MULTI = re.compile(r'哪些|下列哪些|以下哪些|不定项', re.S)
TYPE_SINGLE= re.compile(r'哪一|下列哪项|下列哪一|单选', re.S)
YEAR_RE    = re.compile(r'(?:19|20)\d{2}')

def clean_footnotes(text):
    text = LATEX_FN1.sub('', text)
    text = LATEX_FN2.sub('', text)
    text = INLINE_FN.sub('', text)
    return text

def clean_footnotes_block(region):
    """整块清洗：去脚注 + 去除内容行行首的 markdown 标题 # 前缀（如 ## 【考点】）。"""
    region = clean_footnotes(region)
    lines = [re.sub(r'^#{1,6}\s+', '', ln) for ln in region.split('\n')]
    return '\n'.join(lines)

def trim_trailing(region):
    """裁剪解析块尾部泄漏的结构标题（下一题的『核心考点/一般考点』行、空行、# 标题）。"""
    lines = region.split('\n')
    while lines:
        s = lines[-1].strip()
        if s == '' or HDR_RE.match(lines[-1]) or re.match(r'^\s*(核心考点|一般考点|考点\d+)', s):
            lines.pop()
        else:
            break
    return '\n'.join(lines)

def split_options(region):
    """从题干+选项区域拆出 题干 与 选项列表。返回 (stem, options_dict)。"""
    # 去除行首题号
    region = Q_RE.sub('', region, count=1)
    matches = list(OPT_MARK.finditer(region))
    if not matches:
        return region.strip(), {}
    # 按 A,B,C,D,E 顺序收集（跳过乱序/误判）
    seq = []
    expected = ord('A')
    for m in matches:
        letter = m.group(1)
        if ord(letter) == expected:
            seq.append((letter, m))
            expected += 1
            if letter == 'E':
                break
    if not seq:
        return region.strip(), {}
    first_start = seq[0][1].start()
    stem = region[:first_start].strip()
    options = {}
    for i, (letter, m) in enumerate(seq):
        content_start = m.end()                       # 选项字母+点号之后
        content_end = seq[i+1][1].start() if i+1 < len(seq) else len(region)  # 下一选项标记之前
        val = region[content_start:content_end].strip()
        val = re.sub(r'\s+', ' ', val)
        options[letter] = val
    return stem, options

def extract_answer(text):
    m = ANSWER_RE.search(text)
    if m:
        return re.sub(r'[^A-Za-z]', '', m.group(1)).upper()
    return None

def norm_paragraphs(text):
    # 合并多余空行但保留单空行（0.5 行间距），去除首尾空行
    lines = [ln.rstrip() for ln in text.split('\n')]
    out = []
    blank = False
    for ln in lines:
        if ln.strip() == '':
            if not blank and out:
                out.append('')
                blank = True
            continue
        out.append(ln.strip())
        blank = False
    while out and out[0] == '':
        out.pop(0)
    while out and out[-1] == '':
        out.pop()
    return '\n'.join(out)

def parse():
    questions = []
    cur_chapter = ''
    cur_section = ''
    for fpath in SRC:
        with open(fpath, encoding='utf-8') as f:
            raw_lines = f.read().split('\n')
        # 预处理：剔除脚注块与独立页码行
        lines = []
        for ln in raw_lines:
            if FOOTNOTE_BLOCK.match(ln):
                continue
            if PAGE_NUM.match(ln):
                continue
            lines.append(ln)
        # 第一遍线性扫描：维护 章/节 上下文，并记录每个题号行当时的 章/节
        q_meta = []  # (start_index, chapter, section)
        for i, ln in enumerate(lines):
            mh = HDR_RE.match(ln)
            if mh:
                title = mh.group(1).strip()
                if re.search(r'第.章', title):
                    cur_chapter = title
                    cur_section = ''   # 新章开始，清空旧节
                elif re.search(r'第.节', title):
                    cur_section = title
            if Q_RE.match(ln):
                q_meta.append((i, cur_chapter, cur_section))
        # 第二遍：按题号切块
        for qi, (start, chap, sec) in enumerate(q_meta):
            end = q_meta[qi+1][0] if qi+1 < len(q_meta) else len(lines)
            block = lines[start:end]
            # 定位 考点
            kd_line = None
            for i, ln in enumerate(block):
                if '【考点】' in ln:
                    kd_line = i
                    break
            if kd_line is None:
                # 无结构标记（OCR 损坏）：整段当解析，标草稿
                stem_region = '\n'.join(block)
                stem_region = trim_trailing(clean_footnotes_block(stem_region))
                stem, options = split_options(stem_region)
                analysis = norm_paragraphs(stem_region)
                answer = extract_answer(analysis)
                q = make_question(stem, options, analysis, answer, chap, sec, draft=True)
                questions.append(q)
                continue
            stem_region = '\n'.join(block[:kd_line])
            analysis_region = '\n'.join(block[kd_line:])
            stem_region = clean_footnotes(stem_region)
            analysis_region = trim_trailing(clean_footnotes_block(analysis_region))
            stem, options = split_options(stem_region)
            analysis = norm_paragraphs(analysis_region)
            # 考点单行
            kd_text = ''
            m = KD_RE.search(analysis_region)
            if m:
                kd_text = m.group(1).strip()
            answer = extract_answer(analysis) or extract_answer('\n'.join(block))
            draft = not (len(options) >= 2 and answer)
            # 编章兜底：若章节为空但节存在，用节名补编章
            chap_out = chap if chap else sec
            q = make_question(stem, options, analysis, answer, chap_out, sec,
                              kd_text=kd_text, draft=draft)
            questions.append(q)
    return questions

def make_question(stem, options, analysis, answer, chapter, section, kd_text='', draft=False):
    stem = norm_paragraphs(stem)
    year = ''
    my = YEAR_RE.search(stem)
    if my:
        year = my.group(0)
    # 题型
    if TYPE_MULTI.search(stem) or (answer and len(answer) > 1):
        typ = '多选'
    elif TYPE_SINGLE.search(stem):
        typ = '单选'
    elif answer and len(answer) == 1:
        typ = '单选'
    else:
        typ = '多选' if (answer and len(answer) > 1) else '单选'
    if '不定项' in stem:
        typ = '不定项'
    return {
        '题干': stem,
        '选项A': options.get('A', ''),
        '选项B': options.get('B', ''),
        '选项C': options.get('C', ''),
        '选项D': options.get('D', ''),
        '选项E': options.get('E', ''),
        '答案': answer or '',
        '解析': analysis,
        '考点': kd_text,
        '编章': chapter,
        '章节': section,
        '题型': typ,
        '年份': year,
        '状态': '草稿' if draft else '已发布',
    }

def to_feishu_records(qs):
    recs = []
    for i, q in enumerate(qs, 1):
        opts = []
        for k in ('A', 'B', 'C', 'D', 'E'):
            v = q.get('选项'+k, '')
            if v:
                opts.append(f"{k}. {v}")
        fields = {
            '题目ID': f"sjjz-{i:03d}",
            '科目': '商经知',
            '编章': q['编章'],
            '章节': q['章节'],
            '题型': q['题型'],
            '题干': q['题干'],
            '选项A': q['选项A'],
            '选项B': q['选项B'],
            '选项C': q['选项C'],
            '选项D': q['选项D'],
            '选项E': q['选项E'],
            '答案': q['答案'],
            '解析': q['解析'],
            '考点': q['考点'],
            '难度': '',
            '来源': '2026法大金题解析',
            '年份': q['年份'],
            '状态': q['状态'],
            '排序': i,
            '备注': '',
        }
        recs.append(fields)
    return recs

def main():
    qs = parse()
    recs = to_feishu_records(qs)
    # 输出文件
    parsed = [{'题目ID': r['题目ID'], **{k: r[k] for k in ('科目','编章','章节','题型','题干','选项A','选项B','选项C','选项D','选项E','答案','解析','考点','年份','状态','排序')}}
               for r in recs]
    with open(os.path.join(OUT, 'parsed.json'), 'w', encoding='utf-8') as f:
        json.dump(parsed, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT, 'feishu_records.json'), 'w', encoding='utf-8') as f:
        json.dump(recs, f, ensure_ascii=False, indent=2)
    # 本地导入包（questions.商经知.import.json）
    import_pkg = {
        'subject': '商经知',
        'total': len(qs),
        'updated': '2026-08-10',
        'questions': parsed,
    }
    with open(os.path.join(OUT, 'questions.商经知.import.json'), 'w', encoding='utf-8') as f:
        json.dump(import_pkg, f, ensure_ascii=False, indent=2)
    # CSV
    import csv
    with open(os.path.join(OUT, '题库.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['题目ID','科目','编章','章节','题型','题干','选项A','选项B','选项C','选项D','选项E','答案','解析','考点','年份','状态','排序'])
        for r in recs:
            w.writerow([r['题目ID'],r['科目'],r['编章'],r['章节'],r['题型'],r['题干'],r['选项A'],r['选项B'],r['选项C'],r['选项D'],r['选项E'],r['答案'],r['解析'],r['考点'],r['年份'],r['状态'],r['排序']])
    # 统计
    from collections import Counter
    status_c = Counter(r['状态'] for r in recs)
    type_c = Counter(r['题型'] for r in recs)
    draft_ids = [r['题目ID'] for r in recs if r['状态'] == '草稿']
    no_opt = [r['题目ID'] for r in recs if not r['选项A'] or sum(1 for k in 'ABCDE' if r['选项'+k]) < 2]
    no_ans = [r['题目ID'] for r in recs if not r['答案']]
    report = []
    report.append(f"# 商经知重导核对报告\n")
    report.append(f"- 解析题数：**{len(qs)}**（丢弃伪题 0）")
    report.append(f"- 状态分布：{dict(status_c)}")
    report.append(f"- 题型分布：{dict(type_c)}")
    report.append(f"- 草稿({len(draft_ids)})：{draft_ids}")
    report.append(f"- 缺选项(<2个)：{no_opt}")
    report.append(f"- 缺答案：{no_ans}")
    report.append(f"- 含 `<table>`：{sum(1 for r in recs if '<table>' in r['解析'])}")
    report.append(f"- 题干/解析残留 [n] 脚注：{sum(1 for r in recs if re.search(r'\[\d+\]', r['题干']+r['解析']))}")
    report.append(f"- 题干/解析残留 $^{{}}$ 脚注：{sum(1 for r in recs if '$^{' in r['题干']+r['解析'])}")
    report.append(f"- 残留 ①②③④：{sum(1 for r in recs if re.search(r'[①②③④]', r['题干']+r['解析']))}")
    # 编章分布
    ch_c = Counter(r['编章'] for r in recs)
    report.append(f"- 编章分布：{dict(ch_c)}")
    with open(os.path.join(OUT, '核对报告.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(report) + '\n')
    print('\n'.join(report))
    print('\nDONE. files in', OUT)

if __name__ == '__main__':
    main()
