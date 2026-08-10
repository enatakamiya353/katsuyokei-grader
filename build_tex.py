# -*- coding: utf-8 -*-
"""build_data.py のランダム抽出結果から mark.tex と answer_key.json を生成する。"""
import json
import re

from build_data import KATSUYOKEI_LETTER, SHURUI_LETTER, build

ZK = "０１２３４５６７８９"


def zk(n):
    return "".join(ZK[int(c)] for c in str(n))


KATSUYOKEI_CHOICES = "ア．未然形　イ．連用形　ウ．終止形　エ．連体形　オ．仮定形　カ．命令形"
SHURUI_CHOICES = "ア．五段活用　イ．上一段活用　ウ．下一段活用　エ．カ行変格活用　オ．サ行変格活用"


def render_sentence(sent):
    """{...} を \\bousen{...} に変換する。"""
    return re.sub(r"\{([^}]*)\}", r"\\bousen{\1}", sent)


def build_section1(sec1):
    items = []
    key = {}
    for i, (cat, sent, exp) in enumerate(sec1, 1):
        letter = KATSUYOKEI_LETTER[cat]
        key[i] = letter
        block = (
            "\\needspace{7em}\n"
            f"\\item[\\textbf{{問{zk(i)}．}}] {render_sentence(sent)}\\\\\n"
            f"{KATSUYOKEI_CHOICES}"
        )
        items.append(block)
        items.append((i, letter, cat, exp))
    return items, key


def main():
    sec1, sec2 = build()
    n1 = len(sec1)

    q_blocks_1, ans_1 = [], []
    for i, (cat, sent, exp) in enumerate(sec1, 1):
        letter = KATSUYOKEI_LETTER[cat]
        ans_1.append((i, letter, cat, exp))
        q_blocks_1.append(
            "\\needspace{7em}\n"
            f"\\item[\\textbf{{問{zk(i)}．}}] {render_sentence(sent)}\\\\\n"
            f"{KATSUYOKEI_CHOICES}"
        )

    q_blocks_2, ans_2 = [], []
    for j, (cat, sent, exp) in enumerate(sec2, 1):
        i = n1 + j
        letter = SHURUI_LETTER[cat]
        ans_2.append((i, letter, cat, exp))
        q_blocks_2.append(
            "\\needspace{7em}\n"
            f"\\item[\\textbf{{問{zk(i)}．}}] {render_sentence(sent)}（活用の種類）\\\\\n"
            f"{SHURUI_CHOICES}"
        )

    answer_key = {str(i): letter for i, letter, _, _ in ans_1 + ans_2}
    with open("answer_key.json", "w", encoding="utf-8") as f:
        json.dump(answer_key, f, ensure_ascii=False, indent=2)
        f.write("\n")

    ans_lines_1 = [
        f"\\item[\\textbf{{問{zk(i)}．}}] \\textbf{{{letter}．{cat}}}　（{exp}）"
        for i, letter, cat, exp in ans_1
    ]
    ans_lines_2 = [
        f"\\item[\\textbf{{問{zk(i)}．}}] \\textbf{{{letter}．{cat}}}　（{exp}）"
        for i, letter, cat, exp in ans_2
    ]

    # マークシート：左＝問1〜10（6択）、右＝問11〜20（11,12は6択／13〜20は5択）
    markrows = []
    for i in range(1, 11):
        left_num, left_n = zk(i), 6
        right_i = i + 10
        right_n = 6 if right_i <= 12 else 5
        markrows.append(f"\\marksrowpair{{{left_num}}}{{{left_n}}}{{{zk(right_i)}}}{{{right_n}}}")
    markrows_tex = "\n".join(markrows)

    tex = f"""\\documentclass[a4paper,tate,11pt,twoside]{{jlreq}}
\\input{{common_preamble}}

\\begin{{document}}
\\pagestyle{{empty}}
\\CoverBorder

\\begin{{center}}
\\vspace*{{1cm}}

{{\\fontsize{{26}}{{34}}\\selectfont \\rmfamily 国語　活用の種類・活用形}} \\\\[3mm]
{{\\Large マークシートテスト（２０問）Ver.３．０}}

\\vspace{{8mm}}

\\ChuiBox

\\vfill

\\begin{{tabular}}{{ll}}
    {{\\Large 学\\qquad 年:}} & \\rule{{7cm}}{{0.5pt}} \\\\[1cm]
    {{\\Large 氏\\qquad 名 :}} & \\rule{{7cm}}{{0.5pt}}
\\end{{tabular}}

\\end{{center}}

\\newpage
\\pagestyle{{plain}}
\\setcounter{{page}}{{1}}

\\needspace{{4em}}
\\textbf{{【１】活用形（６択）　次の各文について、――線部の語の活用形として最も適切なものを、ア〜カから一つ選び、記号で答えなさい。}}
\\vspace{{1em}}

\\begin{{enumerate}}[label=, leftmargin=*, itemsep=1.8em]

{chr(10).join(chr(10) + b for b in q_blocks_1)}

\\end{{enumerate}}

\\newpage

\\needspace{{4em}}
\\textbf{{【２】動詞の活用の種類（５択）　次の各問いについて、あてはまる最も適切なものを、ア〜オから一つ選び、記号で答えなさい。}}
\\vspace{{1em}}

\\begin{{enumerate}}[label=, leftmargin=*, itemsep=1.8em]

{chr(10).join(chr(10) + b for b in q_blocks_2)}

\\end{{enumerate}}

\\newpage

\\pagestyle{{empty}}

{{\\yoko
\\AnswerSheetHeader{{国語 活用の種類・活用形 マークシートテスト Ver.3.0 解答用紙(問1〜問20)}}

\\noindent
\\begin{{tabularx}}{{\\yokowidth}}{{|>{{\\centering\\arraybackslash}}p{{0.8cm}}|X|>{{\\centering\\arraybackslash}}p{{0.8cm}}|X|}}
\\hline
\\textbf{{番号}} & \\centering\\arraybackslash\\textbf{{記号}} & \\textbf{{番号}} & \\centering\\arraybackslash\\textbf{{記号}} \\\\ \\hline
{markrows_tex}
\\end{{tabularx}}
}}

\\newpage
\\tate
\\pagestyle{{plain}}
\\normalfont\\selectfont
\\textbf{{\\Large 解答一覧【国語　活用の種類・活用形　マークシートテスト　Ver.３．０】}}
\\vspace{{2em}}

\\hrule
\\vspace{{2em}}

\\begin{{enumerate}}[label=, leftmargin=*, itemsep=1em]
{chr(10).join(ans_lines_1 + ans_lines_2)}
\\end{{enumerate}}

\\end{{document}}
"""
    with open("mark.tex", "w", encoding="utf-8") as f:
        f.write(tex)
    print("mark.tex, answer_key.json を生成しました。")


if __name__ == "__main__":
    main()
