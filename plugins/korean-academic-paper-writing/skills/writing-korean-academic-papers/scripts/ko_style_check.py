"""Compare a Korean paper draft against the reference corpus (5 KCI papers, 2024).

Usage: python ko_style_check.py DRAFT [--section results]
DRAFT may be .tex, .md or .txt. Tables, figures, captions, comments and LaTeX commands are stripped
before counting, because table and figure text follows a different register (개조체).
Only declarative sentences ending in '다.' with mostly Hangul characters are counted.
"""
import argparse
import re
import sys

# Corpus ranges measured on P1..P5 (see reference/corpus.md), rounded outward from the min and max across the five papers.
TARGETS = [
    # key, label, low, high, how to read
    ("median_len", "문장 길이 중앙값(자)", 65, 90, "짧으면 끊기는 번역투, 길면 만연체"),
    ("present_pct", "현재형 -ㄴ다/-는다 종결(%)", 25, 42, "자기 실험·결과를 현재형으로 쓰면 높아짐"),
    ("past_pct", "과거형 -ㅆ다 종결(하였다·나타났다 등, %)", 20, 45, "실험 논문(P3~P5)은 31~44%, 방법 해설형(P1)은 8%"),
    ("can_pct", "'수 있다/없다' 종결(%)", 5, 20, ""),
    ("anaphor_pct", "문두 지시어 이/이를/이러한/이는(%)", 7, 24, "낮으면 문장끼리 이어지지 않음"),
    ("conj_pct", "문두 접속어 또한/특히/그러나/반면(%)", 9, 20, "낮으면 문단 흐름이 끊김"),
    ("gloss_rate", "한글(English) 병기(/1000문장)", 65, 300, "초록·본문 첫 등장에 한 번씩. 300 초과면 반복 병기 확인"),
    ("result_frames", "결과 보고 틀(/1000문장)", 15, 180, "하한만 의미 있음. 결과 장 위주의 부분 원고는 90을 넘을 수 있음"),
    ("question_rate", "물음표 문장(/1000문장)", 0, 35, "수사 의문문은 서론 연구 질문에만"),
]
LLM_MARKERS = {  # rising in KCI abstracts after late 2024 (Lee, arXiv:2609.07447). Corpus rate per 1000 sentences in ().
    "시사하다": r"시사(한다|하였다|했다|하는|함|하며)",
    "확인되었다": r"확인되었다",
    "규명": r"규명",
    "구조적": r"구조적",
    "단순한 X를 넘어": r"단순(한|히)\s*\S+\s*넘어",
    "이러한 결과는": r"이러한\s*결과는",
    "핵심": r"핵심",
    "중요한 역할": r"중요한\s*역할",
    "실질적": r"실질적",
    "기능하다": r"기능(한다|하였다|하는)",
}
TRANSLATION_MARKERS = {  # English discourse frames carried into Korean; 0 in the five corpus papers unless noted.
    "'지침/규칙은 단순하다'": r"(지침|원칙|규칙)은\s*(단순|간단)하다",
    "'주요 결과는 다음과 같다'": r"주요\s*결과는\s*다음과\s*같다",
    "'예상대로'": r"예상대로",
    "'그렇다면' 의문": r"그렇다면\s",
    "괄호 안 콜론 뜻풀이": r"[가-힣A-Za-z]\(([^()]{1,30}):\s[^()]+\)",
    "'A가 아니라 B이다' 단정": r"(이|가)\s*아니라\s*\S+(이다|이었다)$",
    "'~에 의해' 피동": r"에\s*의해",
    "'LLM 모델' 중복": r"LLM\s*모델",
}


def strip_tex(t):
    if r"\begin{abstract}" in t:
        t = t[t.find(r"\begin{abstract}"):]
    t = re.sub(r"(?m)(?<!\\)%.*$", "", t)
    for env in [r"table\*", "table", r"figure\*", "figure", "tikzpicture", "keywords", "tabular"]:
        t = re.sub(r"\\begin\{" + env + r"\}.*?\\end\{" + env + r"\}", " ", t, flags=re.S)
    t = re.sub(r"\\bibliography\{[^}]*\}|\\bibliographystyle\{[^}]*\}", " ", t)
    t = re.sub(r"~?\\cite\{[^}]*\}", "", t)
    t = re.sub(r"\\ref\{[^}]*\}", "1", t)
    t = re.sub(r"\\(section\*?|subsection\*?)\{([^}]*)\}", "\n\n", t)  # headings are not sentences
    t = re.sub(r"\\(textit|textbf)\{[^}]{1,30}\.\}", " ", t)  # run-in paragraph heads like \textit{한계.}
    t = re.sub(r"\\(emph|textit|textbf)\{([^}]*)\}", r"\2", t)
    t = re.sub(r"\$([^$]*)\$", r"\1", t)
    t = re.sub(r"\\[,;!]|\\quad|\\dots", " ", t)
    t = re.sub(r"\\item", "\n", t)
    t = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?(\{[^}]*\})?", " ", t)
    return t.replace("{", "").replace("}", "").replace("~", " ").replace("\\%", "%")


def strip_md(t):
    t = re.sub(r"(?m)^\s*\|.*\|\s*$", " ", t)          # markdown tables
    t = re.sub(r"(?m)^\s*#+\s*.*$", "\n", t)            # headings are not sentences
    t = re.sub(r"(?m)^\s*(\*\*)?(표|그림|Table|Figure)\s*\d+[.:)].*$", " ", t)  # captions
    return t.replace("**", "").replace("`", "")


def sentences(t):
    t = re.sub(r"\s*\n\s*", " ", t)
    t = re.sub(r"\s?\[[0-9][0-9,\-–\s]*\]", "", t)          # numeric citations: 구분된다[1]. -> 구분된다.
    # Trailing parenthesis such as 낮아진다(4.1절). is moved out so the sentence still ends in 다;
    # statistics such as 보였다(p < 0.05). are kept inside the sentence for the significance check.
    t = re.sub(r"다\s?(\([^()]{0,60}\))\s?\.",
               lambda m: "다" + m.group(1) + "다." if re.search(r"p\s*[<=>]|CI|신뢰|t\s*=", m.group(1)) else "다.", t)
    out = []
    for s in re.split(r"(?<=다)\.\s+|(?<=다)\.$|(?<=다)\.(?=[가-힣A-Z(])", t):
        s = s.strip()
        if len(s) < 8 or not s.endswith("다"):
            continue
        h = len(re.findall(r"[가-힣]", s))
        a = len(re.findall(r"[A-Za-z]", s))
        if h < 6 or h < a:
            continue
        out.append(s[-400:])
    return out


CAN = r"수\s*(있|없)(다|었다)$"


def final_coda(s):
    """Coda (final consonant) index of the syllable before the closing '다'; -1 if not Hangul."""
    s = re.sub(r"\([^()]*\)다$", "", s)  # undo the kept statistics parenthesis: 보였다(p < 0.05)다 -> 보였다
    if len(s) < 2 or not s.endswith("다"):
        return -1
    c = ord(s[-2]) - 0xAC00
    return c % 28 if 0 <= c < 11172 else -1


def is_past(s):
    # 하였다, 나타났다, 낮아졌다 ...: syllable before 다 ends in ㅆ (index 20), except 있다.
    return final_coda(s) == 20 and not s.endswith("있다")


def is_present(s):
    # 한다, 된다, 나타낸다, 않는다 ...: syllable before 다 ends in ㄴ (index 4).
    return final_coda(s) == 4 and not re.search(CAN, s)
ANAPH = {"이", "이를", "이러한", "이는", "이에", "이처럼", "이때", "이와", "이로", "이로써", "그", "그러므로"}
CONJ = {"또한", "특히", "그러나", "하지만", "반면", "한편", "따라서", "즉", "예를", "다만", "그리고", "결과적으로"}
RESULT = r"(보였다|나타났다|알\s*수\s*있|확인할\s*수\s*있|나타낸다|확인하였다|확인했다)"


def measure(S):
    n = max(len(S), 1)
    first = [re.split(r"[\s,]", s.strip(), maxsplit=1)[0] for s in S]
    lens = sorted(len(s) for s in S)
    joined = " ".join(S)
    can = sum(1 for s in S if re.search(CAN, s))
    return {
        "n": len(S),
        "median_len": lens[len(lens) // 2] if lens else 0,
        "present_pct": round(100 * sum(1 for s in S if is_present(s)) / n, 1),
        "past_pct": round(100 * sum(1 for s in S if is_past(s)) / n, 1),
        "can_pct": round(100 * can / n, 1),
        "anaphor_pct": round(100 * sum(1 for w in first if w in ANAPH) / n, 1),
        "conj_pct": round(100 * sum(1 for w in first if w in CONJ) / n, 1),
        "gloss_rate": round(1000 * len(re.findall(r"[가-힣]+\s?\([A-Za-z][A-Za-z0-9 ,.@\-]*\)", joined)) / n, 1),
        "result_frames": round(1000 * len(re.findall(RESULT, joined)) / n, 1),
        "question_rate": round(1000 * len(re.findall(r"\?", joined)) / n, 1),
        "markers": {k: len(re.findall(rx, joined)) for k, rx in LLM_MARKERS.items()},
        "translation": {k: sum(len(re.findall(rx, s)) for s in S) for k, rx in TRANSLATION_MARKERS.items()},
        # "유의" claims with no test, p-value or interval in the same sentence (phrasebank 8.7).
        "bare_signif": [s for s in S if re.search(r"유의(한|하게|미한|미하게)", s)
                        and not re.search(r"p\s*[<=>]|p\s*값|p-?value|신뢰\s*구간|검정|CI|\[", s)],
        # Differences of percentage metrics written in % rather than %p (phrasebank 8.3); may also be relative gains.
        "pct_diff": [s for s in S if re.search(r"\d(\.\d+)?\s?%\s*(더\s*)?(높|낮|향상|개선|하락|감소|상승)", s)],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("draft")
    a = ap.parse_args()
    raw = open(a.draft, encoding="utf-8").read()
    if a.draft.endswith(".tex"):
        text = strip_tex(raw)
    elif a.draft.endswith(".md"):
        text = strip_md(raw)
    else:
        text = raw
    m = measure(sentences(text))
    note = " (60개 미만: 비율 지표는 참고만 함)" if m["n"] < 60 else ""
    lines = [f"# 한국어 논문 문체 점검: {a.draft}", f"문장 {m['n']}개(표·그림·캡션 제외){note}", "",
             "| 지표 | 원고 | 기준 범위 | 판정 | 읽는 법 |", "|---|---|---|---|---|"]
    for key, label, lo, hi, note in TARGETS:
        v = m[key]
        verdict = "범위 안" if lo <= v <= hi else ("낮음" if v < lo else "높음")
        lines.append(f"| {label} | {v:g} | {lo}~{hi} | {verdict} | {note} |")
    hits = {k: v for k, v in m["markers"].items() if v}
    rate = 1000 * sum(hits.values()) / max(m["n"], 1)
    lines += ["", f"LLM 문체 표지 합계 {sum(hits.values())}회({rate:.0f}/1000문장, 기준 말뭉치 0~59/1000, 평균 27): "
              + (", ".join(f"{k} {v}" for k, v in hits.items()) or "없음")]
    lines.append(f"통계 표기 점검: 근거(검정·p값·신뢰구간) 없는 '유의' 문장 {len(m['bare_signif'])}개, "
                 f"'N% 높/낮/향상' 문장 {len(m['pct_diff'])}개(%p 또는 상대 개선율 기준 확인)")
    for s in (m["bare_signif"] + m["pct_diff"])[:6]:
        lines.append(f"  - ...{s[-70:]}")
    tr = {k: v for k, v in m["translation"].items() if v}
    lines.append("번역투 표지(기준 논문 5편 합계: 괄호 안 콜론 1(P1), '~에 의해' 2, 'LLM 모델' 32, 나머지 0): "
                 + (", ".join(f"{k} {v}" for k, v in tr.items()) or "없음"))
    em = raw.count("\u2014")
    lines.append(f"엠대시(U+2014): {em}개" + (" (제거 필요)" if em else ""))
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
