# -*- coding: utf-8 -*-
"""
解析 4 份「2026QX客观真金题册理论法-陈璐琼」MinerU OCR markdown，
按用户规则重导飞书「理论法」科目。

规则（用户 2026-08-10）：
- 先删除飞书旧理论法（见 delete_lilunfa.py），本脚本只负责重导。
- 答案优先取「本题答案为」后面的字母；若无则取「【答案】」或「【答案」后面的字母。
- 选项 ABCD 在一个自然段的，每一个选项另起一行（数据层拆成 选项A~E 字段）。
- 题目和解析两端对齐（前端 CSS 控制，数据层不处理）。
- 「考点」「解析」合并在「解析」字段中呈现（解析段保留【考点】…【解析】…）。
- 编章 = 第X部分（法理学/宪法学/司法制度与职业道德/习近平法治思想）；
  章节 = 最近的 ## 考点 X / ## 第X节 小节标题。
- 仅做轻量清洗：去掉 解析 段尾泄漏的 markdown 标题行、独立答案行、[n]/$^{[n]}$ 内联脚注。
  不删 ①②③④（理论法多为法条项号，按先例保留）。
"""
import os, re, json
from collections import Counter

SRC = [
    r"D:/新建文件夹 (2)/2026QX客观真金题册理论法-陈璐琼_Password_Removed(OCR)(OCR)_1-46.pdf-af6b6551-e193-496d-9ab3-169435ed8ad2/MinerU_markdown_202608101544556_52daf578.md",
    r"D:/新建文件夹 (2)/2026QX客观真金题册理论法-陈璐琼_Password_Removed(OCR)(OCR)_47-92.pdf-538f703a-3fec-46f3-9c3b-509a1bcf428f/MinerU_markdown_202608101545652_22c7f4c4.md",
    r"D:/新建文件夹 (2)/2026QX客观真金题册理论法-陈璐琼_Password_Removed(OCR)(OCR)_93-138.pdf-b33771a8-a5a4-4a5a-b247-46df7535b7f3/MinerU_markdown_202608101546382_48af4c70.md",
    r"D:/新建文件夹 (2)/2026QX客观真金题册理论法-陈璐琼_Password_Removed(OCR)(OCR)_139-182.pdf-1a7998f3-a2b5-4770-a3d9-f13c1f858ae1/MinerU_markdown_202608101546930_8b453978.md",
]
OUT = os.path.dirname(os.path.abspath(__file__))

# ---------- 正则 ----------
Q_RE       = re.compile(r'^\s*\d+\.\s')                       # 题号行（仅用于切题干）
Q_START    = re.compile(r'^\s*\d+\.\s*\(\d{4}')               # 题目起始（含年份括号，避免误切解析内编号）
PART_RE    = re.compile(r'第[一二三四五六七八九十]+部分\s*(.*)')
HDR_RE     = re.compile(r'^#{1,6}\s+(.*)$')
KD_INLINE  = re.compile(r'【考点')                            # 行内是否含考点（用于判断是否为 per-question 考点行）
SEC_HDR    = re.compile(r'^#{1,6}\s+(.*)$')
OPT_MARK   = re.compile(r'(?<![A-Za-z])([A-E])\.(?![A-Za-z])')  # 选项字母+点号，其后非字母即视为选项起始
INLINE_FN  = re.compile(r'\[\d+\]')                           # [1] 内联脚注
LATEX_FN1  = re.compile(r'\$\s*\^\{\[[0-9]+\]\}\s*\$')
LATEX_FN2  = re.compile(r'\^\{\[[0-9]+\]\}')
# 答案：优先级1 本题答案为(含本题答案) / 优先级2 【答案】或【答案
ANS1       = re.compile(r'本题答案为?\s*[:：]?\s*([A-Ea-e]+)')
ANS2       = re.compile(r'(?:【)?答案】?\s*[:：]?\s*([A-Ea-e]+)')  # 兼容【答案】AB / 【答案AB / 答案D（无括号）
ANS3       = re.compile(r'\\mathrm\s*\{\s*\\?([A-Ea-e])\s*\}')     # 兼容 LaTeX 答案 $\mathrm { B } _ { \circ }$
# 独立答案行（用于从题干/解析中剔除）
ANS_LINE   = re.compile(r'(?:#{1,6}\s*)?【答案】?\s*[:：]?\s*[A-Ea-e]+')
KD_SPLIT   = re.compile(r'【考点')
KD_TEXT    = re.compile(r'【考点[)】]?\s*(.*?)\s*(?:【解析|$)', re.S)
TYPE_MULTI = re.compile(r'哪些|下列哪些|以下哪些|不定项|多选', re.S)
TYPE_SINGLE= re.compile(r'哪一|下列哪项|下列哪一|单选', re.S)
YEAR_RE    = re.compile(r'(?:19|20)\d{2}')

def dedup_repeat(text, min_len=6, window=3000, protect=None):
    """消除 OCR 重影：归一空白后，若某位置起的长串在更后方再次完整出现，删掉第二份。
    仅删 >=min_len 的精确重复，避免误伤正常文本。
    protect: 受保护字符集合（如选项标记 A. ~ E.），删除第二份时若会吞掉这些字符则跳过本次删除。
    """
    if not text:
        return text
    s = re.sub(r'\s+', '', text)  # 先去掉所有空白（OCR 换行/空格碎片）再找重复
    if len(s) < min_len * 2:
        return s
    i = 0
    n = len(s)
    while i < n:
        best_len = 0
        best_j = -1
        end = min(i + window, n)
        for j in range(i + min_len, end):
            # 保护：删除区间 [j, j+best_len) 不能包含受保护字符
            if protect is not None and any(c in protect for c in s[j:j + min(best_len, n - j)]):
                continue
            L = 0
            while i + L < end and j + L < n and s[i + L] == s[j + L]:
                L += 1
            if L >= min_len and L > best_len:
                best_len = L
                best_j = j
        if best_j >= 0:
            # 二次确认不删保护字符
            if protect is not None and any(c in protect for c in s[best_j:best_j + best_len]):
                i += 1
                continue
            s = s[:best_j] + s[best_j + best_len:]
            n = len(s)
            # 不前进 i，继续检查该位置是否还有别的重复
        else:
            i += 1
    return s

def clean_footnotes(text):
    text = LATEX_FN1.sub('', text)
    text = LATEX_FN2.sub('', text)
    text = INLINE_FN.sub('', text)
    return text

def clean_part(t):
    # 去掉开头所有 "第X部分"（可能嵌套重复，如 第一部分第一部分）
    t = re.sub(r'^第[一二三四五六七八九十]+部分\s*', '', t)
    t = t.strip()
    # 去重（如 法理学法理学）
    if len(t) >= 2 and len(t) % 2 == 0 and t[:len(t)//2] == t[len(t)//2:]:
        t = t[:len(t)//2]
    return t.strip() or '理论法'

def clean_section(t):
    t = t.strip()
    t = re.sub(r'(考点[一二三四五六七八九十]+)\1', r'\1', t)   # 考点三考点三 -> 考点三
    t = re.sub(r'^考点[一二三四五六七八九十]*\s*', '', t)        # 去掉前缀 考点[数字]
    t = t.strip()
    if len(t) >= 4 and len(t) % 2 == 0 and t[:len(t)//2] == t[len(t)//2:]:
        t = t[:len(t)//2]
    return t.strip() or '未分类'

def is_section_heading(ln):
    """返回小节标题文本；若不是小节标题（如 per-question 的 ## 【考点】…）返回 None。"""
    m = SEC_HDR.match(ln)
    if not m:
        return None
    t = m.group(1).strip()
    if '【考点' in t:          # 这是题内考点内容，不是小节标题
        return None
    if re.match(r'^考点', t):  # ## 考点 法的概念
        return clean_section(t)
    if re.match(r'^第.节', t): # ## 第一节 …
        return clean_section(t)
    return None

def trim_trailing(region):
    lines = region.split('\n')
    while lines:
        s = lines[-1].strip()
        if s == '' or HDR_RE.match(lines[-1]) or re.match(r'^\s*(核心考点|一般考点|考点\d+)', s):
            lines.pop()
        else:
            break
    return '\n'.join(lines)

def strip_answer_lines(text):
    return ANS_LINE.sub('', text)

def clean_analysis(region):
    """清洗解析段：去答案行、去 markdown 标题噪声行、去行首 # 前缀、去内联脚注、裁尾部。"""
    region = strip_answer_lines(region)
    lines = []
    for ln in region.split('\n'):
        # 删除整行的 markdown 标题噪声（如 ## 考点 XXX / ## 第一节 / # 第X章），但保留 ## 【考点】/## 【解析】/## 【答案】 等以【开头的行
        if re.match(r'^#{1,6}\s+(?!【)', ln):
            continue
        lines.append(re.sub(r'^#{1,6}\s+', '', ln))
    region = '\n'.join(lines)
    region = clean_footnotes(region)
    region = trim_trailing(region)
    return region

def norm_paragraphs(text):
    lines = [ln.rstrip() for ln in text.split('\n')]
    out, blank = [], False
    for ln in lines:
        if ln.strip() == '':
            if not blank and out:
                out.append(''); blank = True
            continue
        out.append(ln.strip()); blank = False
    while out and out[0] == '':
        out.pop(0)
    while out and out[-1] == '':
        out.pop()
    return '\n'.join(out)

def split_options(region):
    region = Q_RE.sub('', region, count=1)
    matches = list(OPT_MARK.finditer(region))
    if not matches:
        return region.strip(), {}
    seq, expected = [], ord('A')
    for m in matches:
        letter = m.group(1)
        if ord(letter) == expected:
            seq.append((letter, m)); expected += 1
            if letter == 'E':
                break
    if not seq:
        return region.strip(), {}
    first_start = seq[0][1].start()
    stem = region[:first_start].strip()
    options = {}
    for i, (letter, m) in enumerate(seq):
        cs = m.end()
        ce = seq[i+1][1].start() if i+1 < len(seq) else len(region)
        val = re.sub(r'\s+', ' ', region[cs:ce].strip())
        options[letter] = val
    return stem, options

def extract_answer(text):
    m = ANS1.search(text)
    if m:
        return re.sub(r'[^A-Za-z]', '', m.group(1)).upper()
    m = ANS2.search(text)
    if m:
        return re.sub(r'[^A-Za-z]', '', m.group(1)).upper()
    m = ANS3.search(text)
    if m:
        return re.sub(r'[^A-Za-z]', '', m.group(1)).upper()
    return None

def extract_kd(analysis):
    m = KD_TEXT.search(analysis)
    return m.group(1).strip() if m else ''

def make_question(stem, options, analysis, answer, chapter, section, kd_text='', draft=False):
    stem = norm_paragraphs(stem)
    year = ''
    my = YEAR_RE.search(stem)
    if my:
        year = my.group(0)
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

def parse():
    questions = []
    cur_part, cur_section = '', '未分类'
    for fpath in SRC:
        with open(fpath, encoding='utf-8') as f:
            raw_lines = f.read().split('\n')
        # 第一遍：维护 编章/章节 上下文，记录每个题号行坐标
        q_meta = []  # (start_index, part, section)
        for i, ln in enumerate(raw_lines):
            mh = HDR_RE.match(ln)
            if mh:
                title = mh.group(1).strip()
                mp = PART_RE.search(title)
                if mp:
                    cur_part = clean_part(mp.group(1))
                    cur_section = '未分类'
                sec = is_section_heading(ln)
                if sec:
                    cur_section = sec
            if Q_START.match(ln):
                q_meta.append((i, cur_part, cur_section))
        # 第二遍：按题号切块
        for qi, (start, part, sec) in enumerate(q_meta):
            end = q_meta[qi+1][0] if qi+1 < len(q_meta) else len(raw_lines)
            block_lines = raw_lines[start:end]
            block_text = '\n'.join(block_lines)
            # 取答案（在剔除答案行之前，用原始整块）
            answer = extract_answer(block_text)
            # 切分 题干 / 解析：优先按首个【考点】，否则按首个【解析】
            m = KD_SPLIT.search(block_text)
            if m:
                stem_region = block_text[:m.start()]
                analysis_region = block_text[m.start():]
            else:
                m2 = re.search(r'【解析', block_text)
                if m2:
                    stem_region = block_text[:m2.start()]
                    analysis_region = block_text[m2.start():]
                else:
                    stem_region = ''
                    analysis_region = block_text
            # 题干：仅对「首个选项标记之前」的题干去重（整块去重会把 A 重影吞掉 B-E，故不整块去重）
            stem_region = strip_answer_lines(stem_region)
            first_opt = OPT_MARK.search(stem_region)
            if first_opt:
                stem_head = stem_region[:first_opt.start()]
                stem_tail = stem_region[first_opt.start():]
                stem_region = dedup_repeat(stem_head) + stem_tail
            else:
                stem_region = dedup_repeat(stem_region)
            stem, options = split_options(stem_region)
            for k in list(options.keys()):
                options[k] = dedup_repeat(options[k])
            # 解析：整块去重（解析里无选项结构，直接清重影）
            analysis_region = dedup_repeat(analysis_region)
            analysis = norm_paragraphs(clean_analysis(analysis_region))
            kd_text = extract_kd(analysis_region)
            # 草稿判定：选项<2 或 无答案
            opts_count = sum(1 for k in 'ABCDE' if options.get(k))
            draft = not (opts_count >= 2 and answer)
            chap = part if part else sec
            questions.append(make_question(stem, options, analysis, answer, chap, sec,
                                           kd_text=kd_text, draft=draft))
    return questions

def to_feishu_records(qs):
    recs = []
    for i, q in enumerate(qs, 1):
        fields = {
            '题目ID': f"lilun-{i:03d}",
            '科目': '理论法',
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
            '来源': '2026QX客观真金题册理论法-陈璐琼',
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
    parsed = [{'题目ID': r['题目ID'], **{k: r[k] for k in ('科目','编章','章节','题型','题干','选项A','选项B','选项C','选项D','选项E','答案','解析','考点','年份','状态','排序')}}
               for r in recs]
    with open(os.path.join(OUT, 'parsed.json'), 'w', encoding='utf-8') as f:
        json.dump(parsed, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT, 'feishu_records.json'), 'w', encoding='utf-8') as f:
        json.dump(recs, f, ensure_ascii=False, indent=2)
    import_pkg = {'subject': '理论法', 'total': len(qs), 'updated': '2026-08-10', 'questions': parsed}
    with open(os.path.join(OUT, 'questions.理论法.import.json'), 'w', encoding='utf-8') as f:
        json.dump(import_pkg, f, ensure_ascii=False, indent=2)
    import csv
    with open(os.path.join(OUT, '题库.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['题目ID','科目','编章','章节','题型','题干','选项A','选项B','选项C','选项D','选项E','答案','解析','考点','年份','状态','排序'])
        for r in recs:
            w.writerow([r['题目ID'],r['科目'],r['编章'],r['章节'],r['题型'],r['题干'],r['选项A'],r['选项B'],r['选项C'],r['选项D'],r['选项E'],r['答案'],r['解析'],r['考点'],r['年份'],r['状态'],r['排序']])
    # 统计
    status_c = Counter(r['状态'] for r in recs)
    type_c = Counter(r['题型'] for r in recs)
    draft_ids = [r['题目ID'] for r in recs if r['状态'] == '草稿']
    no_opt = [r['题目ID'] for r in recs if sum(1 for k in 'ABCDE' if r['选项'+k]) < 2]
    no_ans = [r['题目ID'] for r in recs if not r['答案']]
    ch_c = Counter(r['编章'] for r in recs)
    sec_c = Counter(r['章节'] for r in recs)
    report = []
    report.append(f"# 理论法（陈璐琼）重导核对报告\n")
    report.append(f"- 解析题数：**{len(qs)}**")
    report.append(f"- 状态分布：{dict(status_c)}")
    report.append(f"- 题型分布：{dict(type_c)}")
    report.append(f"- 草稿({len(draft_ids)})：{draft_ids}")
    report.append(f"- 缺选项(<2个)：{no_opt}")
    report.append(f"- 缺答案：{no_ans}")
    report.append(f"- 残留 [n] 脚注：{sum(1 for r in recs if re.search(r'\[\d+\]', r['题干']+r['解析']))}")
    report.append(f"- 编章分布：{dict(ch_c)}")
    report.append(f"- 章节数：{len(sec_c)}")
    with open(os.path.join(OUT, '核对报告.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(report) + '\n')
    print('\n'.join(report))
    print('\nDONE. files in', OUT)

if __name__ == '__main__':
    main()
